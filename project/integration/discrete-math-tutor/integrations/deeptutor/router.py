"""宿主接入入口；课程、权限和上游身份由服务端确定。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .client import BackendUnavailable, DeepTutorBackend

router = APIRouter(prefix="/api/deeptutor", tags=["deeptutor"])


class HostSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(default="legacy", min_length=1, max_length=64)


@router.post("/session")
def bind_session(request: HostSessionRequest):
    from sqlalchemy import select
    from database.database import session_scope
    from database.models import Student

    with session_scope() as db:
        exists = db.scalar(select(Student.student_id).where(Student.student_id == request.student_id))
    if exists is None:
        raise HTTPException(404, "学生账户不存在")
    try:
        return DeepTutorBackend().bind_session(request.student_id, request.session_id)
    except (BackendUnavailable, ValueError) as exc:
        raise HTTPException(503, "DeepTutor 会话服务暂未就绪") from exc


@router.get("/status")
def backend_status():
    try:
        return DeepTutorBackend().status()
    except ValueError as exc:
        raise HTTPException(503, "DeepTutor 本机服务配置无效") from exc


@router.get("/capabilities")
def backend_capabilities():
    try:
        return {"capabilities": DeepTutorBackend().capabilities()}
    except (BackendUnavailable, ValueError) as exc:
        raise HTTPException(503, "DeepTutor 能力服务暂未就绪") from exc
