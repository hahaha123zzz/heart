"""有限关系同步探索与测评接口。"""
from fastapi import APIRouter, Depends, Query
from models.visualization import Scope
from models.relation import CreateRelation, RelationOperation, RelationAnswers,ClosurePreview
from visualization.relation import RelationService
from visualization_api import call

router=APIRouter(prefix='/api/relations')


@router.get('/capabilities')
def capabilities(student_id: str = Query(min_length=1,max_length=64,pattern=r'^[^\r\n\t]+$')):
    return RelationService().capabilities(student_id)


@router.get('')
def list_artifacts(scope: Scope = Depends()):
    return call(lambda:RelationService().list(scope.student_id,scope.session_id))


@router.post('')
def create(request: CreateRelation):
    return call(lambda:RelationService().create(request))


@router.get('/{artifact_id}')
def get(artifact_id: str, scope: Scope = Depends()):
    return call(lambda:RelationService().get(artifact_id,scope.student_id,scope.session_id))


@router.post('/{artifact_id}/operations')
def operate(artifact_id: str, request: RelationOperation):
    return call(lambda:RelationService().operate(artifact_id,request))


@router.post('/{artifact_id}/closure')
def closure(artifact_id:str,request:ClosurePreview):
    return call(lambda:RelationService().closure_preview(artifact_id,request))


@router.post('/{artifact_id}/draft')
def draft(artifact_id: str, request: RelationAnswers):
    return call(lambda:RelationService().save_draft(artifact_id,request))


@router.post('/{artifact_id}/submissions')
def submit(artifact_id: str, request: RelationAnswers):
    return call(lambda:RelationService().submit(artifact_id,request))
