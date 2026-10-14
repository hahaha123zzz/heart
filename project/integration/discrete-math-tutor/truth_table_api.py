"""双变量真值表的受控接口。"""
from fastapi import APIRouter, Depends, Query
from models.visualization import Scope
from models.truth_table import CreateTruthTable, TableAnswers
from visualization.truth_table import TruthTableService
from visualization_api import call

router = APIRouter(prefix='/api/truth-tables')


@router.get('/capabilities')
def capabilities(student_id: str = Query(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$')):
    return TruthTableService().capabilities(student_id)


@router.get('')
def list_tables(scope: Scope = Depends()):
    return call(lambda: TruthTableService().list(scope.student_id, scope.session_id))


@router.post('')
def create(request: CreateTruthTable):
    return call(lambda: TruthTableService().create(request))


@router.get('/{artifact_id}')
def get(artifact_id: str, scope: Scope = Depends()):
    return call(lambda: TruthTableService().get(artifact_id, scope.student_id, scope.session_id))


@router.post('/{artifact_id}/draft')
def draft(artifact_id: str, request: TableAnswers):
    return call(lambda: TruthTableService().save_draft(artifact_id, request))


@router.post('/{artifact_id}/submissions')
def submit(artifact_id: str, request: TableAnswers):
    return call(lambda: TruthTableService().submit(artifact_id, request))
