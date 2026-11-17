"""教材知识图谱（只读）：按章节返回 LightRAG 的有界子图。

鉴权复用厂家 JWT（`dt_token`），用标准库做 HS256 校验，不引入额外依赖。
本接口只返回教材结构与实体描述，不含任何学生成绩。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

router = APIRouter(prefix="/api/graph")
_engine = None

WORKSPACE = os.getenv("LIGHTRAG_WORKSPACE", "deeptutor_426733019d24d665")
MAX_NODES = 200
COURSE_DIR = Path(__file__).resolve().parent / "knowledge" / "courses" / "experimental-psychology-3"
_kc_entity: dict[str, list[str]] | None = None
_kc_names: dict[str, str] | None = None


def _kc_lookup() -> tuple[dict[str, list[str]], dict[str, str]]:
    global _kc_entity, _kc_names
    if _kc_entity is None or _kc_names is None:
        try:
            mapping = json.loads(
                (COURSE_DIR / "kc_entity_map.json").read_text(encoding="utf-8"))
            registry = json.loads(
                (COURSE_DIR / "kc_registry_full.json").read_text(encoding="utf-8"))
            _kc_entity = {row["entity"]: row["kc_ids"] for row in mapping.get("mappings") or []}
            _kc_names = {item["id"]: item["name"] for item in registry["knowledge_components"]}
        except (OSError, ValueError):
            _kc_entity, _kc_names = {}, {}
    return _kc_entity, _kc_names


def _rag_engine():
    global _engine
    if _engine is None:
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "heart")
        password = os.getenv("POSTGRES_PASSWORD", "")
        database = os.getenv("POSTGRES_DATABASE", "heart_rag")
        _engine = create_engine(
            f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}",
            pool_pre_ping=True)
    return _engine


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _auth_secret() -> str:
    home = os.getenv("DEEPTUTOR_HOME") or str(
        Path(__file__).resolve().parents[2] / ".runtime" / "deeptutor")
    path = Path(home) / "data" / "system" / "auth" / "auth_secret"
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except OSError:
        secret = ""
    if not secret:
        raise HTTPException(503, "鉴权密钥不可用")
    return secret


def require_student(dt_token: str | None = Cookie(default=None, alias="dt_token")) -> str:
    if not dt_token:
        raise HTTPException(401, "未登录")
    try:
        header_b64, payload_b64, signature_b64 = dt_token.split(".")
    except ValueError:
        raise HTTPException(401, "凭证格式不正确") from None

    expected = hmac.new(
        _auth_secret().encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("ascii"),
        hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64decode(signature_b64)):
        raise HTTPException(401, "凭证无效")
    try:
        claims = json.loads(_b64decode(payload_b64))
    except ValueError:
        raise HTTPException(401, "凭证内容无效") from None
    if float(claims.get("exp") or 0) < time.time():
        raise HTTPException(401, "登录已过期")
    return str(claims.get("username") or "")


@router.get("/subgraph")
def subgraph(
    chapter: int | None = Query(default=None, ge=1, le=99),
    q: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=80, ge=10, le=MAX_NODES),
    student: str = Depends(require_student),
):
    file_path = f"chapter_{chapter:02d}.generated.pdf" if chapter else None
    params = {"workspace": WORKSPACE, "limit": limit + 1, "file_path": file_path,
              "pattern": f"%{q.strip()}%" if q and q.strip() else None}
    sql = """
        select id, properties
        from lightrag_graph_nodes
        where namespace = 'chunk_entity_relation' and workspace = :workspace
          and (cast(:file_path as text) is null or properties->>'file_path' = :file_path)
          and (cast(:pattern as text) is null or id ilike :pattern)
        order by updated_at desc
        limit :limit
    """
    with _rag_engine().connect() as conn:
        rows = conn.execute(text(sql), params).all()
        truncated = len(rows) > limit
        rows = rows[:limit]
        ids = [row[0] for row in rows]
        edges: list[dict] = []
        if ids:
            edge_sql = """
                select src_id, tgt_id, properties
                from lightrag_graph_edges
                where workspace = :workspace and src_id = any(:ids) and tgt_id = any(:ids)
                limit 600
            """
            for source, target, props in conn.execute(
                    text(edge_sql), {"workspace": WORKSPACE, "ids": ids}).all():
                edges.append({
                    "source": source, "target": target,
                    "weight": float((props or {}).get("weight") or 1.0),
                    "description": str((props or {}).get("description") or ""),
                })
    entity_map, names = _kc_lookup()
    nodes = [{
        "id": row[0],
        "type": str((row[1] or {}).get("entity_type") or ""),
        "description": str((row[1] or {}).get("description") or ""),
        "chapter": str((row[1] or {}).get("file_path") or ""),
        "kc_ids": entity_map.get(row[0], []),
        "kc_names": [names[kc] for kc in entity_map.get(row[0], []) if kc in names],
    } for row in rows]
    return {"nodes": nodes, "edges": edges, "truncated": truncated,
            "total_returned": len(nodes), "chapter": chapter}
