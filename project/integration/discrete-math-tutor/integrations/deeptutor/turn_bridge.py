"""复用上游回合和事件存储；这里只记录已保存宿主任务的版本化投影。"""
from contextlib import contextmanager
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException

from .session_bridge import SessionBridge, SessionBindingRequest, require_bridge_token
from .turn_contract import TurnCursor, TurnProjection


@contextmanager
def scoped_store(bridge, user_id):
    from deeptutor.multi_user.models import CurrentUser, UserScope
    from deeptutor.multi_user.paths import user_context
    from deeptutor.services.session import get_sqlite_session_store

    scope = UserScope("user", user_id, bridge.root / "users" / user_id)
    with user_context(CurrentUser(user_id, user_id, "student", scope)):
        yield get_sqlite_session_store()


def turn_id(session_id, task_id, revision):
    key = json.dumps([session_id, task_id, revision], separators=(",", ":"))
    return "heart_turn_" + hashlib.sha256(key.encode()).hexdigest()


class TurnBridge:
    def __init__(self, sessions: SessionBridge):
        self.sessions = sessions

    async def publish(self, request: TurnProjection):
        binding = await self.sessions.bind(SessionBindingRequest.model_validate(
            request.model_dump(include=set(SessionBindingRequest.model_fields))))
        identifier = turn_id(binding["session_id"], request.task_id, request.task_revision)
        metadata = {"host_task_id": request.task_id, "host_task_revision": request.task_revision,
                    "outcome": request.outcome, "result_digest": request.result_digest}
        events = [
            {"type": "sources", "seq": 1, "source": "heart", "content": "",
             "metadata": {"sources": [source.model_dump() for source in request.sources]}},
            {"type": "done", "seq": 2, "source": "heart", "content": "", "metadata": metadata},
        ]
        async with self.sessions.lock:
            with scoped_store(self.sessions, binding["user_id"]) as store:
                existing = await store.get_turn(identifier)
                status = "completed" if request.outcome == "awaiting_clarification" else request.outcome
                if existing is None:
                    # 投影不执行模型；未完成的旧副本只能来自中断的同步操作。
                    active = await store.get_active_turn(binding["session_id"])
                    if active:
                        capability = active.get("capability", "")
                        previous_status = capability.removeprefix("heart_snapshot:")
                        if not capability.startswith("heart_snapshot:") or previous_status not in {"completed", "failed", "cancelled"}:
                            raise HTTPException(409, "上游会话有正在执行的任务")
                        await store.transition_turn(active["id"], previous_status)
                    await store.begin_turn(binding["session_id"], "heart_snapshot:" + status, turn_id=identifier)
                try:
                    await store.append_events(identifier, events)
                except ValueError as exc:
                    raise HTTPException(409, "相同任务版本的回合内容发生冲突") from exc
                if not await store.transition_turn(identifier, status):
                    raise HTTPException(409, "上游回合状态发生冲突")
                row = await store.get_turn(identifier)
        return {**binding, "turn_id": identifier, "last_seq": row["last_seq"],
                "task_id": request.task_id, "task_revision": request.task_revision}

    async def events(self, request: TurnCursor):
        # 恢复不建立新身份、课程或会话。
        with self.sessions._connect() as db:
            row = db.execute("""SELECT u.upstream_id, s.upstream_id FROM users u
                JOIN sessions s ON s.user_id=u.upstream_id
                WHERE u.host_id=? AND s.course_id=? AND s.host_id=?""",
                (request.student_id, request.course_id, request.session_id)).fetchone()
        if row is None:
            raise HTTPException(404, "回合不存在")
        user_id, session_id = row
        identifier = turn_id(session_id, request.task_id, request.task_revision)
        async with self.sessions.lock:
            with scoped_store(self.sessions, user_id) as store:
                turn = await store.get_turn(identifier)
                if turn is None or turn["session_id"] != session_id:
                    raise HTTPException(404, "回合不存在")
                events = await store.get_events(identifier, after_seq=request.after_seq)
        return {"turn_id": identifier, "last_seq": turn["last_seq"], "events": events}


def install_turn_bridge(app, sessions: SessionBridge):
    bridge = TurnBridge(sessions)
    router = APIRouter(prefix="/internal/heart", dependencies=[Depends(require_bridge_token)])
    router.add_api_route("/turn", bridge.publish, methods=["POST"])
    router.add_api_route("/turn/events", bridge.events, methods=["POST"])
    app.include_router(router)
