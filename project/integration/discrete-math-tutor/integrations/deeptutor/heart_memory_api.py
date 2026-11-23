"""学生记忆管理与厂家读写适配；H PostgreSQL 是唯一正文来源。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from deeptutor.api.routers.auth import TokenPayload, require_auth
from integrations.deeptutor import student_memory as memory


class PreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)


class MemorySettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)


def _owner(payload):
    if not payload or not payload.username or not payload.user_id:
        raise HTTPException(401, "请先登录")
    return payload.username, payload.user_id


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        if str(exc) == "memory_identity_changed":
            raise HTTPException(409, "记忆身份绑定已变化，请联系管理员核对。") from None
        raise HTTPException(400, "记忆内容无效，请检查后重试。") from None
    except Exception:
        raise HTTPException(503, "记忆服务暂不可用，请稍后重试；聊天仍可继续。") from None


def install_heart_memory(app) -> None:
    memory.ensure_tables()
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.memory.store import set_external_memory_store
    from deeptutor.services.memory.paths import set_external_memory_root_guard, MemoryAccessDisabledError

    def external_store():
        user = get_current_user_or_none()
        return memory.StudentMemoryStore(user.username, user.id) if user and not user.is_admin else None

    def guard_local_memory():
        user = get_current_user_or_none()
        if user and not user.is_admin:
            raise MemoryAccessDisabledError("学生长期记忆统一由 H 保存，厂家本地记忆已关闭。")

    set_external_memory_store(external_store)
    set_external_memory_root_guard(guard_local_memory)
    from deeptutor.runtime.turn_engine import set_external_context_preparer
    from deeptutor.services.session.context_builder import set_external_history_handlers
    async def prepare_context(context):
        await memory.prepare_turn(context)
        from integrations.deeptutor.assessment_delivery import prepare_control
        await prepare_control(context)
    set_external_context_preparer(prepare_context)
    set_external_history_handlers(memory.prepare_history, memory.wrap_summary)
    previous = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with previous(application) as state:
            task = asyncio.create_task(memory.index_loop())
            try:
                yield state
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    app.router.lifespan_context = lifespan

    async def memory_denied(request, exc):
        return JSONResponse({"detail": "请通过我的记忆页管理记忆。"}, status_code=403)
    app.add_exception_handler(MemoryAccessDisabledError, memory_denied)
    router = APIRouter(prefix="/api/heart/memory", dependencies=[Depends(require_auth)])

    @router.get("")
    def read_memory(response: Response, q: str = Query(default="", max_length=100), payload: TokenPayload = Depends(require_auth)) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return _call(memory.overview, *_owner(payload), search=q.strip())

    @router.get("/settings")
    def read_settings(response: Response, payload: TokenPayload = Depends(require_auth)) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return _call(memory.settings, *_owner(payload))

    @router.put("/settings")
    def save_settings(body: MemorySettingsRequest, payload: TokenPayload = Depends(require_auth)) -> dict:
        return _call(memory.set_enabled, *_owner(payload), body.enabled)

    @router.post("/preference")
    def add_preference(body: PreferenceRequest, payload: TokenPayload = Depends(require_auth)) -> dict:
        owner = _owner(payload)
        _call(memory.add_preference, *owner, body.text)
        return {"ok": True, "preferences": _call(memory.overview, *owner)["preferences"]}

    @router.delete("/{kind}/{entry_id}")
    def delete_memory(kind: str, entry_id: int, payload: TokenPayload = Depends(require_auth)) -> dict:
        if kind not in {"preference", "profile"} or entry_id <= 0:
            raise HTTPException(404, "条目不存在")
        owner = _owner(payload)
        if not _call(memory.delete_entry, *owner, kind, entry_id):
            raise HTTPException(404, "条目不存在")
        return {"deleted": str(entry_id), "preferences": _call(memory.overview, *owner)["preferences"]}

    app.include_router(router)
