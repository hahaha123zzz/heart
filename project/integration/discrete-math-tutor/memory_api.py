"""本机测试账户记忆管理；生产身份认证接入前不开放 production 账户。"""
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, ConfigDict, Field
from web_api import _student_id

router=APIRouter(prefix="/api/students/{student_id}/memory",tags=["学习记忆管理"])


class MisconceptionCorrection(BaseModel):
    model_config=ConfigDict(extra="forbid")
    note: str=Field(min_length=1,max_length=1000)


def memory(student_id):
    _student_id(student_id)
    from main import orchestrator
    kind=orchestrator.memory.repo.get_account_type(student_id)
    if kind is None:
        raise HTTPException(404,"学生不存在")
    if kind!="test":
        raise HTTPException(403,"当前记忆管理仅开放本机测试账户")
    return orchestrator.memory


def execute(call):
    try:
        return call()
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get("")
def overview(student_id: str, point: str | None=Query(None,min_length=1,max_length=128)):
    service=memory(student_id)
    return execute(lambda:service.memory_overview(student_id,point))


@router.post("/misconceptions/{item_id}/correction")
def correct(student_id: str, request: MisconceptionCorrection, item_id: int=Path(gt=0)):
    service=memory(student_id)
    return execute(lambda:service.dispute_misconception(student_id,item_id,request.note))


@router.delete("/preferences/{key}")
def remove_preference(student_id: str,key: str):
    service=memory(student_id)
    execute(lambda:service.forget_preference(student_id,key))
    return {"ok":True}


@router.delete("/points")
def remove_point(student_id: str,point: str=Query(min_length=1,max_length=128)):
    service=memory(student_id)
    return execute(lambda:service.forget_point(student_id,point))
