"""真值表状态与判题；复用现有逻辑求值、账户、事务及记忆接口。"""
from uuid import uuid4
from sqlalchemy import select
from database.database import session_scope
from database.models import TruthTableRow, TruthTableOperationRow
from database.account_manager import AccountManager
from knowledge.course import get_section
from knowledge.exercise_graders import logic_tree, logic_value
from visualization.service import VisualizationService, VisualizationError, digest
from knowledge.course_config import PSYCHOLOGY

POINT = 'legacy:truth-table' if PSYCHOLOGY else get_section(4, 3)['title']
FORMULAS = {'and': 'p∧q', 'or': 'p∨q', 'implies': 'p→q', 'equivalent': 'p↔q', 'not-or': '¬p∨q'}
ROWS = {a+b: {'p': a == '1', 'q': b == '1'} for a in '01' for b in '01'}


def results(template):
    tree = logic_tree(FORMULAS[template])
    return {key: logic_value(tree, assignment) for key, assignment in ROWS.items()}


class TruthTableService(VisualizationService):
    operation_model = TruthTableOperationRow
    def capabilities(self, student_id):
        return {'enabled': self.enabled(student_id), 'epoch': self.repo.memory_epoch(student_id, POINT),
                'templates': [{'id': key, 'formula': value} for key, value in FORMULAS.items()]}

    def load_row(self, session, artifact_id, student_id, session_id):
        row = session.scalar(select(TruthTableRow).where(TruthTableRow.id == artifact_id,
            TruthTableRow.student_id == student_id, TruthTableRow.session_id == session_id))
        if row is None or self.repo.memory_epoch(student_id, POINT) != row.epoch:
            raise VisualizationError(404, '真值表不存在、已删除或不属于当前会话')
        return row

    def public(self, row):
        return {'artifact_id': row.id, 'conversation_id': row.conversation_id, 'component_type': 'truth_table',
                'schema_version': 1, 'origin': 'auxiliary_example', 'template_id': row.template_id,
                'formula': FORMULAS[row.template_id], 'knowledge_point': POINT, 'revision': row.revision,
                'mode': row.mode, 'rows': [{'id': key, 'assignment': value} for key, value in ROWS.items()],
                'draft': row.draft, 'correction_of': row.correction_of, 'feedback': row.submission,
                'evaluation': results(row.template_id) if row.mode == 'explore' or row.submission else None,
                'readonly': not self.enabled(row.student_id)}

    def list(self, student_id, session_id):
        with session_scope() as session:
            rows = session.scalars(select(TruthTableRow).where(TruthTableRow.student_id == student_id,
                TruthTableRow.session_id == session_id).order_by(TruthTableRow.conversation_id.desc()).limit(40)).all()
            return [self.public(row) for row in rows if self.repo.memory_epoch(student_id, POINT) == row.epoch]

    def create(self, request):
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            fingerprint = digest(request.model_dump())
            old = session.scalar(select(TruthTableRow).where(TruthTableRow.student_id == request.student_id,
                TruthTableRow.session_id == request.session_id, TruthTableRow.request_id == request.request_id))
            if old and old.payload_hash != fingerprint:
                raise VisualizationError(409, '同一请求编号不能用于不同内容')
            if self.repo.memory_epoch(request.student_id, POINT) != request.expected_epoch:
                raise VisualizationError(409, '知识点记忆已变化，请重新打开真值表')
            if old:
                return self.public(old)
            template = request.template_id
            draft = {'values': dict.fromkeys(ROWS), 'explanation': ''}
            if request.correction_of:
                original = self.load_row(session, request.correction_of, request.student_id, request.session_id)
                if original.submission is None:
                    raise VisualizationError(409, '请先提交原表，再开始订正')
                template, draft = original.template_id, original.draft
            AccountManager(self.repo).create_test_account(request.student_id)
            session.flush()
            content = ('订正真值表：修改原答案后再次提交，按辅助作答记录。' if request.correction_of else
                       '真值表辅助练习：'+FORMULAS[template]+'。填写每行结果；选中一行可以向 AI 提问。')
            message = self.repo.append_conversation(request.student_id, 'assistant', content)
            row = TruthTableRow(id=str(uuid4()), student_id=request.student_id, session_id=request.session_id,
                request_id=request.request_id, payload_hash=fingerprint, conversation_id=message,
                knowledge_point=POINT, epoch=request.expected_epoch, template_id=template, mode=request.mode,
                correction_of=request.correction_of, revision=1, assisted=bool(request.correction_of) or request.mode == 'explore', draft=draft)
            session.add(row)
            self.repo.record_event(request.student_id, 'truth-table:'+row.id, POINT, 'truth_table_created',
                {'artifact_id': row.id, 'conversation_id': message, 'correction_of': request.correction_of})
            session.flush()
            return self.public(row)

    def save_draft(self, artifact_id, request):
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            row = self.load_row(session, artifact_id, request.student_id, request.session_id)
            fingerprint = digest(request.model_dump())
            receipt_model = self.operation_model
            old = session.scalar(select(receipt_model).where(receipt_model.artifact_id == artifact_id,
                receipt_model.request_id == request.request_id))
            if old:
                if old.payload_hash != fingerprint:
                    raise VisualizationError(409, '同一请求编号不能用于不同内容')
                return old.result
            self.check_answers(row, request)
            row.draft = request.model_dump(include={'values', 'explanation'})
            row.revision += 1
            result = self.public(row)
            session.add(receipt_model(id=str(uuid4()), artifact_id=row.id,
                request_id=request.request_id, payload_hash=fingerprint, result=result))
            session.flush()
            return result

    @staticmethod
    def check_answers(row, request):
        if row.submission is not None:
            raise VisualizationError(409, '此表已提交，请点击订正这道题')
        if row.revision != request.expected_revision:
            raise VisualizationError(409, '真值表已变化，请重新加载')
        if set(request.values) != set(ROWS):
            raise VisualizationError(422, '请且仅填写当前四种真值指派')

    def submit(self, artifact_id, request):
        from memory.memory_manager import MemoryManager
        from memory.evidence_policy import assess_graph_attempt
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            row = self.load_row(session, artifact_id, request.student_id, request.session_id)
            fingerprint = digest(request.model_dump())
            if row.submission is not None:
                if row.submit_request_id == request.request_id and row.submit_payload_hash == fingerprint:
                    return row.submission
                raise VisualizationError(409, '此表已提交，请点击订正这道题')
            self.check_answers(row, request)
            if any(value is None for value in request.values.values()):
                raise VisualizationError(422, '请填写全部四行后再提交')
            expected = results(row.template_id)
            checks = {key: request.values[key] == value for key, value in expected.items()}
            decision = assess_graph_attempt(row.assisted)
            row.draft = request.model_dump(include={'values', 'explanation'})
            payload = {'artifact_id': row.id, 'revision': row.revision, 'formula': FORMULAS[row.template_id],
                'answers': row.draft, 'expected': expected, 'checks': checks, 'assisted': row.assisted,
                'validator_version': 'logic-tree-v1', 'independent': decision.independent, 'eligible': decision.eligible}
            event_id = MemoryManager(self.repo).record_truth_table_submission(request.student_id, POINT, row.id,
                payload, expected_epoch=row.epoch)
            row.submission = dict(payload, event_id=event_id, correct=all(checks.values()),
                explanation_verified=False, mastery_updated=False, step_advanced=False)
            row.submit_request_id, row.submit_payload_hash = request.request_id, fingerprint
            # 提交改变展示和教学范围，应使在途提示快照失效。
            row.revision += 1
            session.flush()
            return row.submission

    def snapshot(self, target, student_id, session_id, *, mark_assisted=True):
        self.require_enabled(student_id)
        with session_scope(immediate=True) as session:
            row = self.load_row(session, target.artifact_id, student_id, session_id)
            if row.revision != target.expected_revision:
                raise VisualizationError(409, '真值表已变化，请加载最新版本再提问')
            if mark_assisted and row.submission is None:
                row.assisted = True
                session.flush()
            return {'artifact_id': row.id, 'revision': row.revision, 'epoch': row.epoch,
                'formula': FORMULAS[row.template_id], 'row_id': target.row_id, 'assignment': ROWS[target.row_id],
                'student_value': row.draft['values'][target.row_id], 'evaluation': results(row.template_id),
                'answer_scope': 'hint' if row.mode == 'assessment' and row.submission is None else 'full'}

    def guard_snapshot(self, snapshot, student_id, session_id):
        self.require_enabled(student_id)
        with session_scope() as session:
            row = self.load_row(session, snapshot['artifact_id'], student_id, session_id)
            if row.revision != snapshot['revision'] or row.epoch != snapshot['epoch']:
                raise VisualizationError(409, '提问期间真值表已变化，请按当前行重新提问')
