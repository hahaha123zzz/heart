"""固定图测评：服务端出题、隐藏答案、一次提交及原子学习证据。"""
import secrets
from sqlalchemy import select
from database.database import session_scope
from database.models import GraphAttemptRow
from memory.evidence_policy import assess_graph_attempt
from memory.memory_manager import MemoryManager
from models.visualization import GraphSpec
from visualization.graph_validator import evaluate_graph, SEMANTICS


def assessment_graph():
    # 在审核过的环、路径、星形、环加对角线之间出题；不返回题型名。
    variants = [((1,2),(2,3),(3,4),(4,1)), ((1,2),(2,3),(3,4)),
                ((1,2),(1,3),(1,4)), ((1,2),(2,3),(3,4),(4,1),(1,3))]
    labels = secrets.SystemRandom().sample([1,2,3,4], 4)
    return GraphSpec(nodes=[{'id':f'v{i}', 'label':f'v{i}'} for i in range(1,5)],
        edges=[{'source':f'v{labels[a-1]}', 'target':f'v{labels[b-1]}'} for a,b in secrets.choice(variants)])


def attempt_for(session, artifact_id):
    return session.scalar(select(GraphAttemptRow).where(GraphAttemptRow.artifact_id == artifact_id))


def submit(service, artifact_id, request):
    from visualization.service import digest, VisualizationError
    service.require_enabled(request.student_id)
    with session_scope(immediate=True) as session:
        row = service.load_row(session, artifact_id, request.student_id, request.session_id)
        attempt = attempt_for(session, artifact_id)
        if attempt is None:
            raise VisualizationError(422, '请先打开一张新测评图')
        fingerprint = digest(request.model_dump())
        if attempt.submission is not None:
            if attempt.request_id != request.request_id or attempt.payload_hash != fingerprint:
                raise VisualizationError(409, '本图已经提交，请打开新测评图继续练习')
            return attempt.submission
        if row.revision != request.expected_revision:
            raise VisualizationError(409, '测评图版本已变化，请重新加载')
        graph = GraphSpec.model_validate(row.graph)
        if set(request.degrees) != {node.id for node in graph.nodes}:
            raise VisualizationError(422, '请提交当前所有顶点的度数')
        evaluation = evaluate_graph(graph)
        expected = {'degrees': evaluation['degrees'], 'connected': evaluation['connected'],
                    'prediction': 'circuit' if evaluation['has_euler_circuit'] else
                                  'open_path' if evaluation['has_open_euler_path'] else 'neither'}
        answers = request.model_dump(include={'degrees','connected','prediction','explanation'})
        checks = {field: answers[field] == expected[field] for field in expected}
        decision = assess_graph_attempt(attempt.assisted)
        payload = {'artifact_id': artifact_id, 'revision': row.revision, 'epoch': row.epoch,
                   'graph': row.graph, 'answers': answers, 'expected': expected,
                   'checks': checks, 'assisted': attempt.assisted, 'validator_version': SEMANTICS,
                   'independent': decision.independent, 'eligible': decision.eligible,
                   'verification': decision.verification}
        event_id = MemoryManager(service.repo).record_graph_submission(request.student_id,
            row.knowledge_point, attempt.id, payload, expected_epoch=row.epoch)
        result = {'attempt_id': attempt.id, 'event_id': event_id, **payload,
                  'correct': all(checks.values()), 'evaluation': evaluation,
                  'explanation_verified': False, 'evidence_reason': decision.reason,
                  'step_advanced': False, 'mastery_updated': False}
        attempt.request_id = request.request_id
        attempt.payload_hash = fingerprint
        attempt.submission = result
        session.flush()
        return result
