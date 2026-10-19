"""仅复用上游知识库的搜索/读取，不向宿主开放笔记写入工具。"""
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .published_course import read_pack
from .session_bridge import require_bridge_token


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms: list[str] = Field(min_length=1, max_length=8)
    limit: int = Field(default=6, ge=1, le=12)


def search(home: Path, request: KnowledgeQuery):
    from deeptutor.capabilities.obsidian.vault import search_notes, read_note

    if any(not 1 <= len(term) <= 100 for term in request.terms): raise ValueError("知识库查询词无效")
    directory, manifest = read_pack(home)
    root = directory / "vault"
    scores = {}
    for term in dict.fromkeys(request.terms):
        for rank, hit in enumerate(search_notes(root, term, limit=30), start=1):
            relative = hit["path"]
            if relative not in manifest["files"]: raise ValueError("检索资源不属于发布教材")
            note = read_note(root, relative)
            chunk_id = manifest["files"][relative]["chunk_id"]
            if note["frontmatter"].get("id") != chunk_id: raise ValueError("教材块身份已变化")
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (60 + rank)
    return {"course_id": manifest["course_id"], "version": manifest["version"],
        "index_sha256": manifest["source_hashes"]["index"], "vector_indexed": False,
        "chunk_ids": sorted(scores, key=lambda key: (-scores[key], key))[:request.limit]}


def install_knowledge_bridge(app, home):
    router = APIRouter(prefix="/internal/heart/knowledge", dependencies=[Depends(require_bridge_token)])

    @router.post("/search")
    async def search_course(request: KnowledgeQuery):
        try:
            return await asyncio.to_thread(search, home, request)
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(503, "教材知识库未发布或校验失败") from exc

    app.include_router(router)
