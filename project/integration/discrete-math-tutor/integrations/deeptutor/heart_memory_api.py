"""学生记忆：只暴露 L3 的偏好与画像条目（隐藏 L1/L2 与层级/文件概念）。

- 查看：偏好 + 画像的自然语言条目
- 删除：按条目 id 删除
- 添加：写入学习偏好（引擎自带去重与原子写）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deeptutor.api.routers.auth import TokenPayload, require_auth
from deeptutor.services.memory.store import get_memory_store

KINDS = {"preference": "preferences", "profile": "profile"}


class PreferenceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def _entries(key: str) -> list[dict]:
    doc = get_memory_store().read_doc("L3", key)
    return [{"id": entry.id, "text": entry.text} for entry in doc.all_entries()]


def install_heart_memory(app) -> None:
    router = APIRouter(prefix="/api/heart/memory", dependencies=[Depends(require_auth)])

    @router.get("")
    def read_memory(payload: TokenPayload = Depends(require_auth)) -> dict:
        return {
            "preferences": _entries("preferences"),
            "profile": _entries("profile"),
        }

    @router.post("/preference")
    async def add_preference(
        body: PreferenceRequest, payload: TokenPayload = Depends(require_auth)
    ) -> dict:
        report = await get_memory_store().write_preference(
            op="add", text=body.text.strip(), trace_id="chat")
        if not report.accepted:
            raise HTTPException(400, "偏好未保存")
        return {"ok": True, "preferences": _entries("preferences")}

    @router.delete("/{kind}/{entry_id}")
    async def delete_memory(
        kind: str, entry_id: str, payload: TokenPayload = Depends(require_auth)
    ) -> dict:
        key = KINDS.get(kind)
        if key is None:
            raise HTTPException(404, "未知的记忆类别")
        removed = await get_memory_store().delete_entry("L3", key, entry_id)
        if not removed:
            raise HTTPException(404, "条目不存在")
        return {"deleted": entry_id, "preferences": _entries("preferences")}

    app.include_router(router)
