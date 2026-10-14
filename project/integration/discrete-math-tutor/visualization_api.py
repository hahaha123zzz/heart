"""本机测试账户的固定模板互动接口；账户鉴权沿用 Demo 约定。"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from models.visualization import CreateVisualization, GraphOperation, GraphSubmission, Scope
from visualization.service import VisualizationService, VisualizationError

router = APIRouter(prefix='/api/visualizations')


def call(action):
    try:
        return action()
    except VisualizationError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except IntegrityError as exc:
        if getattr(exc.orig, 'sqlite_errorname', '') == 'SQLITE_CONSTRAINT_UNIQUE' or getattr(exc.orig, 'sqlstate', '') == '23505':
            raise HTTPException(409, '请求同时发生，请重试原请求') from exc
        raise


@router.get('/capabilities')
def capabilities(student_id: str = Query(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$')):
    return VisualizationService().capabilities(student_id)


@router.get('')
def list_artifacts(student_id: str = Query(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$'), session_id: str = Query(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$')):
    scope = Scope(student_id=student_id, session_id=session_id)
    return call(lambda: VisualizationService().list(scope.student_id, scope.session_id))


@router.post('')
def create_artifact(request: CreateVisualization):
    return call(lambda: VisualizationService().create(request))


@router.get('/{artifact_id}')
def get_artifact(artifact_id: str, student_id: str = Query(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$'), session_id: str = Query(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$')):
    scope = Scope(student_id=student_id, session_id=session_id)
    return call(lambda: VisualizationService().get(artifact_id, scope.student_id, scope.session_id))


@router.post('/{artifact_id}/operations')
def operate(artifact_id: str, request: GraphOperation):
    return call(lambda: VisualizationService().operate(artifact_id, request))


@router.post('/{artifact_id}/submissions')
def submit_graph(artifact_id: str, request: GraphSubmission):
    from visualization.assessment import submit
    return call(lambda: submit(VisualizationService(), artifact_id, request))
