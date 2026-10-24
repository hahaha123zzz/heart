"""Q5 binding 上的本次活动状态；命令日志、事务和路径身份复用既有 SQL 服务。"""
from copy import deepcopy
import hashlib
import json
from sqlalchemy import inspect, select, update
from database.database import session_scope
from database.q5_learning import Q5BindingRow, Q5PathRow, Q5CommandRow
from models.session_study_plan import SessionStudyPlan


def _schema(session):
    return any(c['name'] == 'session_plan' for c in inspect(session.connection()).get_columns('q5_learning_bindings'))


def validate_source(ref):
    from knowledge.course_navigation import validate
    from knowledge.pdf_reader import document_for_chapter
    if ref.get('source_kind') != 'q2_navigation':
        return False
    try:
        unit = validate({'id': ref['unit_id'], 'version': ref['version']})
        record = document_for_chapter(unit['chapter_id'])
        return bool(record and ref.get('document_id') == record['document_id'] and
                    ref.get('chapter_id')==unit['chapter_id'] and ref.get('section_id')==unit['section_id'])
    except (ValueError, KeyError, OSError):
        return False


class SessionStudyService:
    def __init__(self, scope, *, source_validator=None):
        self.scope = scope
        self.source_validator = source_validator or validate_source

    def ready(self):
        with session_scope() as session:
            return _schema(session)

    def current(self):
        with session_scope() as session:
            if not _schema(session):
                return None
            row = session.get(Q5BindingRow, (self.scope.student_id, self.scope.session_id))
            return deepcopy(row.session_plan) if row and row.session_plan else None

    def validate(self, value):
        plan = SessionStudyPlan.model_validate(value)
        if (plan.student_id, plan.session_id, plan.course_id) != (self.scope.student_id, self.scope.session_id, self.scope.course_id):
            raise ValueError('session_plan_owner_mismatch')
        refs={json.dumps(ref,sort_keys=True):ref for item in plan.items for ref in item.source_refs}
        if not all(self.source_validator(ref) for ref in refs.values()):
            raise ValueError('session_plan_source_unavailable')
        return plan

    def guard(self, value):
        plan = self.validate(value)
        with session_scope() as session:
            binding = session.get(Q5BindingRow, (self.scope.student_id, self.scope.session_id))
            current = binding.session_plan if binding and _schema(session) else None
            if not current or current['plan_id'] != plan.plan_id or current['revision'] != plan.revision:
                raise ValueError('session_plan_revision_conflict')
            self._path_guard(session, binding, plan)

    def _path_guard(self, session, binding, plan):
        if (binding.active_path_id or None) != plan.path_id:
            raise ValueError('session_plan_path_changed')
        if plan.path_id:
            path = session.get(Q5PathRow, plan.path_id)
            if path is None or path.student_id != self.scope.student_id or path.revision != plan.path_revision:
                raise ValueError('session_plan_path_revision_conflict')

    def confirm(self, value, *, command_id, guard=lambda: None):
        plan = self.validate(value)
        if plan.status != 'draft':
            raise ValueError('session_plan_not_draft')
        return self._write(plan, command_id, 'confirm', guard)

    def explained(self, value, *, command_id, guard=lambda: None):
        plan = self.validate(value)
        if plan.status != 'active' or not plan.current_item_id:
            raise ValueError('session_plan_not_active')
        for item in plan.items:
            if item.item_id == plan.current_item_id:
                item.status = 'explained'
        return self._write(plan, command_id, 'explained', guard)

    def transition(self, value):
        """预演下一活动，不写库；只有成功发布后 explained 才提交。"""
        plan = self.validate(value)
        current = next((i for i in plan.items if i.item_id == plan.current_item_id), None)
        if current is None or current.status != 'explained':
            raise ValueError('session_plan_explanation_required')
        current.status = 'done'
        following = next((i for i in plan.items if i.status == 'planned'), None)
        plan.current_item_id = following.item_id if following else None
        if following:
            following.status = 'in_progress'
        else:
            plan.status = 'done'
        return plan.model_dump()

    def finish(self, value, *, command_id, guard=lambda: None):
        plan = self.validate(value)
        if plan.status != 'done' or plan.current_item_id is not None:
            raise ValueError('session_plan_not_done')
        return self._write(plan, command_id, 'finish', guard)

    def set_mode(self, value, mode, *, command_id, guard=lambda: None):
        plan = self.validate(value)
        if mode not in ('active', 'paused') or plan.status not in ('active','paused'):
            raise ValueError('session_plan_mode_invalid')
        plan.status = mode
        return self._write(plan, command_id, 'mode', guard)

    def _write(self, plan, command_id, operation, guard):
        if not command_id:
            raise ValueError('command_id_required')
        key = 'sp:' + hashlib.sha256((self.scope.session_id + ':' + command_id).encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps([operation, plan.model_dump()], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with session_scope(immediate=True) as session:
            if not _schema(session):
                raise ValueError('session_plan_schema_required: 请先运行显式增量迁移')
            replay = session.scalar(select(Q5CommandRow).where(Q5CommandRow.student_id==self.scope.student_id, Q5CommandRow.command_id==key))
            if replay:
                if replay.result['fingerprint'] != fingerprint:
                    raise ValueError('session_plan_command_conflict')
                return deepcopy(replay.result['plan'])
            guard()
            binding = session.get(Q5BindingRow, (self.scope.student_id, self.scope.session_id))
            if binding is None:
                binding = Q5BindingRow(student_id=self.scope.student_id, session_id=self.scope.session_id, active_path_id='')
                session.add(binding); session.flush()
            current = binding.session_plan or {}
            if operation == 'confirm':
                if current.get('plan_id') != plan.base_plan_id or current.get('revision', 0) != plan.base_revision:
                    raise ValueError('session_plan_revision_conflict')
                plan.status = 'active'
                first = next((i for i in plan.items if i.status in ('planned','in_progress','explained')), None)
                plan.current_item_id = first.item_id if first else None
                if first and first.status == 'planned':
                    first.status = 'in_progress'
            else:
                if current.get('plan_id') != plan.plan_id or current.get('revision') != plan.revision:
                    raise ValueError('session_plan_revision_conflict')
                plan.revision += 1
            self._path_guard(session, binding, plan)
            payload = plan.model_dump()
            expected = binding.revision
            changed = session.execute(update(Q5BindingRow).where(Q5BindingRow.student_id==self.scope.student_id,
                Q5BindingRow.session_id==self.scope.session_id, Q5BindingRow.revision==expected).values(
                    session_plan=payload, revision=expected+1))
            if changed.rowcount != 1:
                raise ValueError('session_plan_revision_conflict')
            session.add(Q5CommandRow(student_id=self.scope.student_id, command_id=key, command_type='session_'+operation,
                result={'fingerprint':fingerprint,'plan':payload}))
            return payload

    def target(self, value):
        from agents.q3_navigation import LearningTarget
        plan = self.validate(value)
        item = next((i for i in plan.items if i.item_id == plan.current_item_id), None)
        if not item:
            return None
        ref = item.source_refs[0]
        return LearningTarget(target_id='session:'+item.item_id, name=item.title,
            chapter_id=ref.get('chapter_id'), section_id=ref.get('section_id'), version=ref['version'],
            source_scope={'source_refs':item.source_refs,'session_plan_id':plan.plan_id,'session_item_id':item.item_id},
            reason='已确认的本次学习安排')
