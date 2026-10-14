"""任务状态事务，不调用模型、不推断学生能力。"""
import datetime as dt
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select, update
from database.database import session_scope
from database.models import LearningTaskRow, TaskRequestRow, Student

ACTIVE = ("ready", "executing", "awaiting_clarification")


class TaskConflict(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def snapshot(row):
    return {key: getattr(row, key) for key in ("id", "student_id", "session_id", "knowledge_point", "status", "revision", "epoch",
        "clarification_count", "payload", "context", "routing", "result", "expires_at")}


class LearningTaskRepository:
    def account_type(self, student_id):
        with session_scope() as session:
            return session.scalar(select(Student.account_type).where(Student.student_id == student_id))

    def invalidate_pending(self, student_id, session_id):
        """回滚只撤销待澄清任务，保留表和收据以阻止旧请求复活。"""
        with session_scope(immediate=True) as session:
            rows = session.scalars(select(LearningTaskRow).where(
                LearningTaskRow.student_id == student_id, LearningTaskRow.session_id == session_id,
                LearningTaskRow.status == "awaiting_clarification").with_for_update()).all()
            for row in rows:
                row.status = "cancelled"; row.scope_key = None; row.revision += 1
                row.payload = {}; row.context = {}; row.routing = {}
                row.result = {"reply": "任务模式已关闭，上一个待补充问题已失效，请完整重新提问。",
                    "answer_status": "task_disabled", "step_advanced": False,
                    "task_id": row.id, "task_revision": row.revision}
                session.execute(update(TaskRequestRow).where(TaskRequestRow.task_id == row.id).values(result=row.result))
            return len(rows)

    def rolled_back(self, student_id, session_id):
        """恢复入口已失效旧任务后，仍阻止旧槽位短回复进入旧路由。"""
        with session_scope() as session:
            row = session.scalar(select(LearningTaskRow).where(
                LearningTaskRow.student_id == student_id, LearningTaskRow.session_id == session_id
            ).order_by(LearningTaskRow.created_at.desc()).limit(1))
            return bool(row and row.status == "cancelled" and row.result.get("answer_status") == "task_disabled")

    def _owned(self, session, student_id, session_id, task_id):
        row = session.scalar(select(LearningTaskRow).where(LearningTaskRow.id == task_id,
            LearningTaskRow.student_id == student_id, LearningTaskRow.session_id == session_id).with_for_update())
        if row is None:
            raise TaskConflict("task_not_found", "任务不存在或不属于当前会话")
        return row

    def _live(self, row):
        if row.expires_at <= now():
            raise TaskConflict("task_expired", "任务已过期，请重新提问")
        if row.status not in ACTIVE:
            raise TaskConflict("task_conflict", "任务已结束或取消，请重新提问")

    def _receipt_result(self, row, receipt):
        if row.status in ("ready", "executing"):
            return {"reply": "这个请求正在处理，请稍后恢复。", "answer_status": "task_busy",
                "task_id": row.id, "task_revision": row.revision, "step_advanced": False}
        # 澄清已被后续补充推进时，重发初始请求也只返回最新版本。
        return row.result or receipt.result

    def replay(self, student_id, session_id, request_id, payload, memory_repo):
        """先查请求收据，避免重复请求被误当成新的澄清回复。"""
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with session_scope(immediate=True) as session:
            receipt = session.scalar(select(TaskRequestRow).where(TaskRequestRow.student_id == student_id,
                TaskRequestRow.session_id == session_id, TaskRequestRow.request_id == request_id).with_for_update())
            if receipt is None: return None
            if receipt.payload_hash != digest:
                raise TaskConflict("request_conflict", "同一请求编号不能用于不同内容")
            row = self._owned(session, student_id, session_id, receipt.task_id)
            if row.expires_at <= now(): raise TaskConflict("task_expired", "任务已过期，请重新提问")
            if row.status in ("cancelled", "expired"):
                raise TaskConflict("task_conflict", "任务已结束或取消，请重新提问")
            if memory_repo.memory_epoch(student_id, row.knowledge_point) != row.epoch:
                raise TaskConflict("memory_deleted", "相关记忆已删除，请重新提问")
            return self._receipt_result(row, receipt)

    def resume(self, student_id, session_id, task_id, revision, memory_repo):
        with session_scope(immediate=True) as session:
            row = self._owned(session, student_id, session_id, task_id)
            self._live(row)
            if row.status != "awaiting_clarification" or row.revision != revision:
                raise TaskConflict("task_conflict", "任务版本已变化，请恢复最新任务")
            if memory_repo.memory_epoch(student_id, row.knowledge_point) != row.epoch:
                raise TaskConflict("memory_deleted", "相关记忆已删除，请重新提问")
            return snapshot(row)

    def expire(self, student_id, session_id):
        """按会话惰性清理过期内容；保留收据编号与哈希，阻止旧请求复活。"""
        with session_scope(immediate=True) as session:
            rows = session.scalars(select(LearningTaskRow).where(LearningTaskRow.student_id == student_id,
                LearningTaskRow.session_id == session_id, LearningTaskRow.expires_at <= now(),
                LearningTaskRow.status != "expired").with_for_update()).all()
            for row in rows:
                row.status = "expired"; row.scope_key = None; row.revision += 1
                row.payload = {}; row.context = {}; row.routing = {}; row.result = {}
                session.execute(update(TaskRequestRow).where(TaskRequestRow.task_id == row.id).values(result={}))
            return len(rows)

    def get(self, student_id, session_id, task_id):
        with session_scope() as session:
            return snapshot(self._owned(session, student_id, session_id, task_id))

    def pending(self, student_id, session_id):
        with session_scope() as session:
            row = session.scalar(select(LearningTaskRow).where(LearningTaskRow.student_id == student_id,
                LearningTaskRow.session_id == session_id, LearningTaskRow.status == "awaiting_clarification",
                LearningTaskRow.expires_at > now()).order_by(LearningTaskRow.created_at.desc()))
            return snapshot(row) if row else None

    def recent(self, student_id, session_id):
        with session_scope() as session:
            rows = session.scalars(select(LearningTaskRow).where(LearningTaskRow.student_id == student_id,
                LearningTaskRow.session_id == session_id, LearningTaskRow.status == "completed", LearningTaskRow.expires_at > now()).order_by(LearningTaskRow.created_at.desc()).limit(2)).all()
            return [snapshot(row) for row in reversed(rows)]

    def claim(self, *, student_id, session_id, request_id, payload, point, epoch, memory_repo,
              task_id=None, revision=None, ttl_seconds=1800):
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with session_scope(immediate=True) as session:
            if session.get(Student, student_id) is None:
                raise TaskConflict("account_missing", "账户已删除，请重新打开学习页面")
            receipt = session.scalar(select(TaskRequestRow).where(TaskRequestRow.student_id == student_id,
                TaskRequestRow.session_id == session_id, TaskRequestRow.request_id == request_id).with_for_update())
            if receipt:
                if receipt.payload_hash != digest:
                    raise TaskConflict("request_conflict", "同一请求编号不能用于不同内容")
                row = self._owned(session, student_id, session_id, receipt.task_id)
                if memory_repo.memory_epoch(student_id, row.knowledge_point) != row.epoch:
                    raise TaskConflict("memory_deleted", "相关记忆已删除，请重新提问")
                if row.status in ("cancelled", "expired"):
                    raise TaskConflict("task_conflict", "任务已结束或取消")
                if row.expires_at <= now():
                    raise TaskConflict("task_expired", "任务已过期")
                return snapshot(row), receipt.id, self._receipt_result(row, receipt)
            scope = hashlib.sha256((student_id + "\0" + session_id).encode()).hexdigest()
            if task_id:
                row = self._owned(session, student_id, session_id, task_id)
                self._live(row)
                if row.status != "awaiting_clarification" or row.revision != revision:
                    raise TaskConflict("task_conflict", "任务版本已变化，请恢复最新任务")
                if memory_repo.memory_epoch(student_id, row.knowledge_point) != row.epoch:
                    raise TaskConflict("memory_deleted", "相关记忆已删除，请重新提问")
                if memory_repo.memory_epoch(student_id, point) != epoch:
                    raise TaskConflict("memory_deleted", "所选对象的相关记忆已删除，请重新提问")
                row.knowledge_point = point
                row.epoch = epoch
                row.revision += 1
                row.status = "ready"
            else:
                previous = session.scalar(select(LearningTaskRow).where(LearningTaskRow.scope_key == scope).with_for_update())
                if previous:
                    previous.status = "expired" if previous.expires_at <= now() else "cancelled"
                    previous.scope_key = None
                    previous.revision += 1
                    session.flush()
                if memory_repo.memory_epoch(student_id, point) != epoch:
                    raise TaskConflict("memory_deleted", "相关记忆已删除，请重新提问")
                row = LearningTaskRow(id=str(uuid4()), student_id=student_id, session_id=session_id,
                    scope_key=scope, knowledge_point=point, epoch=epoch, payload=payload,
                    expires_at=now() + dt.timedelta(seconds=ttl_seconds))
                session.add(row)
                session.flush()
            receipt = TaskRequestRow(id=str(uuid4()), student_id=student_id, session_id=session_id,
                request_id=request_id, task_id=row.id, payload_hash=digest)
            session.add(receipt); session.flush()
            return snapshot(row), receipt.id, None

    def guard(self, student_id, session_id, task_id, revision, memory_repo):
        with session_scope(immediate=True) as session:
            row = self._owned(session, student_id, session_id, task_id)
            self._live(row)
            if row.revision != revision or row.status not in ("ready", "executing"):
                raise TaskConflict("task_conflict", "任务已变化，旧结果不会保存")
            if memory_repo.memory_epoch(student_id, row.knowledge_point) != row.epoch:
                raise TaskConflict("memory_deleted", "相关记忆已删除，旧结果不会保存")

    def save(self, *, task, receipt_id, status, result, context=None, routing=None, payload=None, memory_repo=None):
        with session_scope(immediate=True) as session:
            row = self._owned(session, task["student_id"], task["session_id"], task["id"])
            self._live(row)
            if row.revision != task["revision"]:
                raise TaskConflict("task_conflict", "任务已变化")
            if memory_repo is not None and memory_repo.memory_epoch(row.student_id, row.knowledge_point) != row.epoch:
                raise TaskConflict("memory_deleted", "相关记忆已删除，旧结果不会保存")
            row.status = status; row.revision += 1
            if status == "awaiting_clarification": row.clarification_count += 1
            if status not in ACTIVE: row.scope_key = None
            if context is not None: row.context = context
            if routing is not None: row.routing = routing
            if payload is not None: row.payload = payload
            enriched = dict(result, task_id=row.id, task_revision=row.revision)
            row.result = enriched
            if status != "executing": session.get(TaskRequestRow, receipt_id).result = enriched
            session.flush()
            return snapshot(row), enriched

    def cancel(self, student_id, session_id, task_id, revision):
        with session_scope(immediate=True) as session:
            row = self._owned(session, student_id, session_id, task_id)
            self._live(row)
            if row.revision != revision: raise TaskConflict("task_conflict", "任务版本已变化")
            row.status = "cancelled"; row.scope_key = None; row.revision += 1
            row.payload = {}; row.context = {}; row.routing = {}; row.result = {}
            session.execute(update(TaskRequestRow).where(TaskRequestRow.task_id == row.id).values(result={}))
            return {"answer_status": "task_cancelled", "reply": "本次问题已取消。", "task_id": row.id, "task_revision": row.revision}
