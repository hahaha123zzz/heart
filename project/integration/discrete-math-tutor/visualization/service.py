"""审核辅助图的创建、版本保护与操作收据。"""
import hashlib
import json
import os
from uuid import uuid4
from sqlalchemy import select
from database.database import session_scope
from database.models import VisualizationRow, VisualizationOperationRow, VisualizationDisplayRow, GraphAttemptRow
from database.repository import Repository
from database.account_manager import AccountManager
from knowledge.course import get_section
from models.visualization import GraphSpec, GraphEdge
from visualization.graph_validator import evaluate_graph

POINT = get_section(7, 7)['title']
TEMPLATE = 'euler-cycle-v1'


class VisualizationError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def rollout_settings():
    scope = os.getenv('VISUALIZATION_ROLLOUT', 'off').strip().lower()
    if scope not in {'off', 'test', 'allowlist'}:
        raise ValueError('VISUALIZATION_ROLLOUT必须为off/test/allowlist')
    allowed = {value.strip() for value in os.getenv('VISUALIZATION_STUDENT_ALLOWLIST', '').split(',') if value.strip()}
    if scope == 'allowlist' and not allowed:
        raise ValueError('allowlist模式必须指定VISUALIZATION_STUDENT_ALLOWLIST')
    return scope, allowed


class VisualizationService:
    def __init__(self):
        self.repo = Repository()

    def enabled(self, student_id):
        scope, allowed = rollout_settings()
        account = self.repo.get_account_type(student_id)
        if scope == 'test':
            # 新的本机测试账户只在显式创建时建立，GET 不创建账户。
            return account in {None, 'test'}
        return scope == 'allowlist' and student_id in allowed and account == 'test'

    def require_enabled(self, student_id):
        if not self.enabled(student_id):
            raise VisualizationError(403, '互动图尚未对当前账户开放')

    def capabilities(self, student_id):
        return {'enabled': self.enabled(student_id), 'template_id': TEMPLATE,
                'knowledge_point': POINT, 'epoch': self.repo.memory_epoch(student_id, POINT)}

    def public(self, row):
        from visualization.assessment import attempt_for
        with session_scope() as session:
            display = session.get(VisualizationDisplayRow, row.id)
            mode = display.mode if display else 'explore'
            attempt = attempt_for(session, row.id)
            submission = attempt.submission if attempt else None
        event = self.repo.get_event(row.student_id, 'visualization:'+row.id) if attempt else None
        correction = event['payload'].get('correction') if event else None
        evaluation = evaluate_graph(GraphSpec.model_validate(row.graph)) if mode == 'explore' or submission else {
            'reason':'先列出与各顶点相接的边，再计算度数；本图暂不展示最终判定。', 'degrees':{}, 'odd_vertices':[]}
        return {'artifact_id': row.id, 'conversation_id': row.conversation_id, 'schema_version': 1,
                'component_type': 'undirected_graph', 'origin': 'auxiliary_example',
                'template_id': TEMPLATE, 'mode': mode, 'knowledge_point': row.knowledge_point,
                'textbook_location': {'chapter_id': 7, 'section_id': 7, 'section_title': POINT,
                                     'definition': '7.18', 'theorems': ['7.11', '7.12']},
                'revision': row.revision, 'layout_revision': row.layout_revision,
                'graph': row.graph, 'layout': row.layout,
                'evaluation': evaluation,
                'attempt': {'submitted': submission is not None, 'feedback': submission, 'correction': correction} if attempt else None,
                'readonly': not self.enabled(row.student_id)}

    def load_row(self, session, artifact_id, student_id, session_id):
        row = session.scalar(select(VisualizationRow).where(VisualizationRow.id == artifact_id,
            VisualizationRow.student_id == student_id, VisualizationRow.session_id == session_id).with_for_update())
        if row is None or self.repo.memory_epoch(student_id, row.knowledge_point) != row.epoch:
            raise VisualizationError(404, '互动图不存在、已删除或不属于当前会话')
        return row

    def list(self, student_id, session_id):
        with session_scope() as session:
            rows = session.scalars(select(VisualizationRow).where(VisualizationRow.student_id == student_id,
                VisualizationRow.session_id == session_id).order_by(VisualizationRow.conversation_id.desc()).limit(40)).all()
            return [self.public(row) for row in rows if self.repo.memory_epoch(student_id, row.knowledge_point) == row.epoch]

    def get(self, artifact_id, student_id, session_id):
        with session_scope() as session:
            return self.public(self.load_row(session, artifact_id, student_id, session_id))

    def snapshot(self, target, student_id, session_id, *, mark_assisted=True):
        from visualization.assessment import attempt_for
        self.require_enabled(student_id)
        with session_scope(immediate=True) as session:
            row = self.load_row(session, target.artifact_id, student_id, session_id)
            if row.revision != target.expected_revision:
                raise VisualizationError(409, '互动图已变化，请加载最新图再提问')
            attempt = attempt_for(session, row.id)
            if mark_assisted and attempt is not None and attempt.submission is None:
                # 所有针对测评图的 AI 请求均按辅助处理，不能改 action 绕过。
                attempt.assisted = True
                session.flush()
            display = session.get(VisualizationDisplayRow, row.id)
            hint_only = (display is not None and display.mode == 'hint') or (attempt is not None and attempt.submission is None)
            return {'artifact_id': row.id, 'revision': row.revision, 'epoch': row.epoch,
                    'graph': row.graph, 'evaluation': evaluate_graph(GraphSpec.model_validate(row.graph)),
                    'answer_scope': 'hint' if hint_only else 'full'}

    def guard_snapshot(self, snapshot, student_id, session_id):
        self.require_enabled(student_id)
        with session_scope() as session:
            row = self.load_row(session, snapshot['artifact_id'], student_id, session_id)
            if row.revision != snapshot['revision'] or row.epoch != snapshot['epoch']:
                raise VisualizationError(409, '提问期间互动图已变化，本轮没有保存回答；请按当前图重新提问')

    def create(self, request):
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            old = session.scalar(select(VisualizationRow).where(VisualizationRow.student_id == request.student_id,
                VisualizationRow.session_id == request.session_id, VisualizationRow.request_id == request.request_id))
            fingerprint = digest(request.model_dump())
            if old and old.payload_hash != fingerprint:
                raise VisualizationError(409, '同一请求编号不能用于不同内容')
            if self.repo.memory_epoch(request.student_id, POINT) != request.expected_epoch:
                raise VisualizationError(409, '知识点记忆已变化，请重新打开互动图')
            if old:
                return self.public(old)
            AccountManager(self.repo).create_test_account(request.student_id)
            # 新账户与消息没有 ORM relationship，须先写入账户以满足消息外键。
            session.flush()
            graph = GraphSpec.model_validate({'nodes': [{'id': f'v{i}', 'label': f'v{i}'} for i in range(1, 5)],
                'edges': [{'source': a, 'target': b} for a, b in [('v1','v2'),('v2','v3'),('v3','v4'),('v4','v1')]]})
            if request.graph is not None:
                if {node.id for node in request.graph.nodes} != {'v1','v2','v3','v4'}:
                    raise VisualizationError(422, '首个模板仅支持 v1 至 v4 四个顶点')
                graph = request.graph
            if request.mode == 'assessment':
                from visualization.assessment import assessment_graph
                graph = assessment_graph()
            correction = None
            layout = {'v1':{'x':80.,'y':60.},'v2':{'x':260.,'y':60.},'v3':{'x':260.,'y':220.},'v4':{'x':80.,'y':220.}}
            if request.correction_of:
                from visualization.assessment import attempt_for
                original = self.load_row(session, request.correction_of, request.student_id, request.session_id)
                original_attempt = attempt_for(session, original.id)
                if original_attempt is None or original_attempt.submission is None:
                    raise VisualizationError(409, '请先提交原图的判断，再开始订正')
                graph = GraphSpec.model_validate(original.graph)
                layout = original.layout
                correction = {'artifact_id': original.id, 'answers': original_attempt.submission['answers']}
            identifier = str(uuid4())
            message_id = self.repo.append_conversation(request.student_id, 'assistant',
                '订正这道图题：已保留原作答，请修改后重新提交。订正按辅助作答记录。' if correction else
                '辅助示例：欧拉通路与回路。可增删边，也可解释当前图或请求第一步提示。这不是教材原图。')
            row = VisualizationRow(id=identifier, student_id=request.student_id, session_id=request.session_id,
                request_id=request.request_id, payload_hash=fingerprint, conversation_id=message_id,
                knowledge_point=POINT, epoch=request.expected_epoch, graph=graph.model_dump(),
                layout=layout,
                revision=1, layout_revision=1)
            session.add(row)
            session.flush()
            session.add(VisualizationDisplayRow(artifact_id=row.id, mode=request.mode))
            if request.mode == 'assessment':
                session.add(GraphAttemptRow(id=str(uuid4()), artifact_id=row.id, assisted=correction is not None))
            self.repo.record_event(request.student_id, 'visualization:'+identifier, POINT, 'visualization_created',
                {'conversation_id': message_id, 'artifact_id': identifier, 'origin':'auxiliary_example', 'correction': correction})
            session.flush()
            return self.public(row)

    def operate(self, artifact_id, request):
        self.require_enabled(request.student_id)
        with session_scope(immediate=True) as session:
            row = self.load_row(session, artifact_id, request.student_id, request.session_id)
            fingerprint = digest(request.model_dump())
            receipt = session.scalar(select(VisualizationOperationRow).where(
                VisualizationOperationRow.artifact_id == artifact_id, VisualizationOperationRow.request_id == request.request_id))
            if receipt:
                if receipt.payload_hash != fingerprint:
                    raise VisualizationError(409, '同一操作编号不能用于不同内容')
                return receipt.result
            if row.revision != request.expected_revision:
                raise VisualizationError(409, '图已变化，请加载最新版本后再操作')
            spec = GraphSpec.model_validate(row.graph)
            if request.operation == 'layout':
                if row.layout_revision != request.expected_layout_revision:
                    raise VisualizationError(409, '布局已变化，请加载最新版本')
                if set(request.positions) != {node.id for node in spec.nodes}:
                    raise VisualizationError(422, '布局必须且只能包含当前图的所有顶点')
                row.layout = {key: value.model_dump() for key, value in request.positions.items()}
                row.layout_revision += 1
            else:
                display = session.get(VisualizationDisplayRow, row.id)
                if display and display.mode == 'assessment':
                    raise VisualizationError(409, '测评图的边固定；可拖动布局，或打开探索图增删边')
                pair = tuple(sorted((request.source, request.target)))
                ids = {node.id for node in spec.nodes}
                if pair[0] == pair[1] or not set(pair) <= ids:
                    raise VisualizationError(422, '端点无效或存在自环')
                pairs = {(edge.source, edge.target) for edge in spec.edges}
                if request.operation == 'add_edge':
                    if pair in pairs:
                        raise VisualizationError(422, '这条边已存在')
                    pairs.add(pair)
                else:
                    if pair not in pairs:
                        raise VisualizationError(422, '这条边不存在')
                    pairs.remove(pair)
                spec = GraphSpec(nodes=spec.nodes, edges=[GraphEdge(source=a,target=b) for a,b in sorted(pairs)])
                row.graph = spec.model_dump()
                row.revision += 1
            result = self.public(row)
            session.add(VisualizationOperationRow(id=str(uuid4()), artifact_id=artifact_id,
                request_id=request.request_id, payload_hash=fingerprint, result=result))
            session.flush()
            return result
