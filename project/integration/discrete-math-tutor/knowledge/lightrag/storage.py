"""On-disk layout for a LightRAG-backed knowledge base.

Like the GraphRAG/PageIndex pipelines, a LightRAG KB keeps a self-contained
store inside the KB's flat ``version-N`` directory (reused from
``index_versioning`` with a ``None`` signature). That dir is LightRAG's
``working_dir``: LightRAG writes its KV stores, vector DBs and the knowledge
graph there::

    <kb_dir>/version-N/
        kv_store_*.json
        vdb_*.json
        graph_chunk_entity_relation.graphml
        meta.json            # synthetic "ready" marker (see write_meta)

The synthetic ``meta.json`` makes the existing "is this KB initialised?" and
index-versions UI checks treat a LightRAG KB as ready without teaching the
manager about LightRAG internals.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import HostEmbedding as EmbeddingConfig
    from .config import HostEmbedding as EmbeddingSignature

from .file_io import atomic_write_json

logger = logging.getLogger(__name__)

META_FILENAME = "meta.json"
PROVIDER = "lightrag"
ADAPTER_SCHEMA = 2
PUBLISHED_STATE = "published"

# Glob patterns LightRAG writes once it has actually built chunk/vector data.
# A graphml file alone is not enough: LightRAG creates an empty graph at startup
# before any document is successfully processed.
_OUTPUT_GLOBS = ("vdb_*.json", "kv_store_text_chunks.json")
_DOC_STATUS_FILENAME = "kv_store_doc_status.json"
_SUCCESS_STATUSES = {"processed", "completed", "done", "success", "indexed"}
_FAILED_STATUSES = {"failed", "error"}


def working_dir(root_dir: Path) -> Path:
    """LightRAG's working dir == the version-N root."""
    return Path(root_dir)


def _store_root(root_dir: Path) -> Path:
    """Resolve native workspace storage while retaining legacy flat reads."""
    root = Path(root_dir)
    if (root / _DOC_STATUS_FILENAME).exists() or any(root.glob("vdb_*.json")):
        return root
    meta = _read_meta(root)
    workspace = str((meta or {}).get("workspace") or "").strip()
    if not workspace:
        from .engine import workspace_for

        workspace = workspace_for(root)
    candidate = root / workspace
    return candidate if candidate.is_dir() else root


def _workspace(root_dir: Path) -> str:
    meta = _read_meta(Path(root_dir)) or {}
    workspace = str(meta.get("workspace") or "").strip()
    if workspace:
        return workspace
    from .engine import workspace_for

    return workspace_for(Path(root_dir))


def _pg_connect():
    """LightRAG 文档状态所在库；只读就绪与错误摘要。"""
    import psycopg

    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", ""),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=os.getenv("POSTGRES_DATABASE", ""),
        connect_timeout=10,
    )


MANIFEST_TABLE = "lightrag_index_manifest"
INDEX_TABLES = (
    "LIGHTRAG_DOC_FULL",
    "LIGHTRAG_DOC_CHUNKS",
    "LIGHTRAG_FULL_ENTITIES",
    "LIGHTRAG_FULL_RELATIONS",
    "LIGHTRAG_ENTITY_CHUNKS",
    "LIGHTRAG_RELATION_CHUNKS",
    "LIGHTRAG_LLM_CACHE",
    "LIGHTRAG_DOC_STATUS",
    "LIGHTRAG_VDB_CHUNKS",
    "LIGHTRAG_VDB_ENTITY",
    "LIGHTRAG_VDB_RELATION",
)


def _ensure_manifest_table(conn) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
        "workspace TEXT NOT NULL, namespace TEXT NOT NULL, row_count BIGINT NOT NULL, "
        "id_sha256 TEXT NOT NULL, source_signature TEXT NOT NULL DEFAULT '', "
        "imported_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (workspace, namespace))"
    )


def table_fingerprint(conn, workspace: str, namespace: str) -> dict[str, Any]:
    if namespace not in INDEX_TABLES:
        raise ValueError(f"未知的 LightRAG 索引表: {namespace}")
    row = conn.execute(
        f"SELECT count(*), encode(sha256(convert_to(coalesce(string_agg(id, '|' ORDER BY id), ''), 'UTF8')), 'hex') "
        f"FROM {namespace} WHERE workspace = %s",
        (workspace,),
    ).fetchone()
    return {"row_count": int(row[0]), "id_sha256": str(row[1] or "")}


def write_manifest(root_dir: Path, entries: dict[str, dict[str, Any]], *, source_signature: str) -> None:
    workspace = _workspace(Path(root_dir))
    with _pg_connect() as conn:
        _ensure_manifest_table(conn)
        for namespace, entry in entries.items():
            if namespace not in INDEX_TABLES:
                raise ValueError(f"未知的 LightRAG 索引表: {namespace}")
            conn.execute(
                f"INSERT INTO {MANIFEST_TABLE} (workspace, namespace, row_count, id_sha256, source_signature) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (workspace, namespace) DO UPDATE SET row_count = EXCLUDED.row_count, "
                "id_sha256 = EXCLUDED.id_sha256, source_signature = EXCLUDED.source_signature, imported_at = now()",
                (workspace, namespace, int(entry["row_count"]), str(entry["id_sha256"]), source_signature),
            )


def read_manifest(root_dir: Path) -> dict[str, dict[str, Any]]:
    import psycopg

    workspace = _workspace(Path(root_dir))
    try:
        with _pg_connect() as conn:
            _ensure_manifest_table(conn)
            rows = conn.execute(
                f"SELECT namespace, row_count, id_sha256, source_signature FROM {MANIFEST_TABLE} WHERE workspace = %s",
                (workspace,),
            ).fetchall()
    except psycopg.errors.UndefinedTable:
        return {}
    return {
        row[0]: {"row_count": int(row[1]), "id_sha256": str(row[2]), "source_signature": str(row[3])}
        for row in rows
    }


def verify_manifest(root_dir: Path, *, source_signature: str) -> dict[str, dict[str, Any]]:
    entries = read_manifest(root_dir)
    if not entries:
        raise RuntimeError("候选索引缺少 PostgreSQL 清单")
    workspace = _workspace(Path(root_dir))
    with _pg_connect() as conn:
        for namespace, entry in entries.items():
            if entry["source_signature"] != source_signature:
                raise RuntimeError("候选索引清单与源签名不一致")
            current = table_fingerprint(conn, workspace, namespace)
            if current["row_count"] != entry["row_count"]:
                raise RuntimeError(f"候选索引 {namespace} 行数变化")
    return entries


def has_output(root_dir: Path | None) -> bool:
    """True when LightRAG has at least one successfully indexed document."""
    if root_dir is None:
        return False
    payload = _read_doc_status(Path(root_dir))
    if not payload:
        return False
    return bool(_doc_status_has_success(payload))


def _doc_status_has_success(payload: dict[str, Any]) -> bool:
    saw_failure = False
    for item in payload.values():
        if not isinstance(item, dict):
            continue
        chunks = item.get("chunks_list")
        if isinstance(chunks, list) and len(chunks) > 0:
            return True
        status = str(item.get("status") or "").lower()
        if status in _SUCCESS_STATUSES:
            return True
        if status in _FAILED_STATUSES:
            saw_failure = True

    return False if saw_failure else None


def failure_summary(root_dir: Path | None, *, limit: int = 3) -> str:
    """Return a short human-readable summary of failed LightRAG documents."""
    if root_dir is None:
        return ""
    payload = _read_doc_status(_store_root(Path(root_dir)))
    if not payload:
        return ""

    failures: list[str] = []
    for item in payload.values():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        error = str(item.get("error_msg") or "").strip()
        if status not in _FAILED_STATUSES and not error:
            continue
        name = str(item.get("file_path") or "document").strip()
        failures.append(f"{name}: {error or status}")
        if len(failures) >= limit:
            break
    return "; ".join(failures)


def document_error(root_dir: Path | None, doc_id: str) -> str:
    """Return the stored LightRAG error for one document, if present."""
    if root_dir is None or not doc_id:
        return ""
    payload = _read_doc_status(_store_root(Path(root_dir)))
    if not payload:
        return ""
    item = payload.get(doc_id)
    if not isinstance(item, dict):
        return ""
    status = str(item.get("status") or "").lower()
    error = str(item.get("error_msg") or "").strip()
    if status in _FAILED_STATUSES or error:
        return error or status
    return ""


def _read_doc_status(root_dir: Path) -> dict[str, Any] | None:
    workspace = _workspace(root_dir)
    try:
        import psycopg

        with _pg_connect() as conn:
            rows = conn.execute(
                "SELECT id, status, chunks_list, error_msg, file_path, content_summary, chunks_count "
                "FROM lightrag_doc_status WHERE workspace = %s",
                (workspace,),
            ).fetchall()
    except psycopg.errors.UndefinedTable:
        return None
    if not rows:
        return None
    keys = ("status", "chunks_list", "error_msg", "file_path", "content_summary", "chunks_count")
    return {row[0]: dict(zip(keys, row[1:])) for row in rows}


def has_any_doc_status(root_dir: Path | None) -> bool:
    if root_dir is None:
        return False
    payload = _read_doc_status(_store_root(Path(root_dir)))
    return bool(payload)


def _read_meta(root_dir: Path) -> dict[str, Any] | None:
    path = Path(root_dir) / META_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def meta_is_native_published(root_dir: Path | None) -> bool:
    if root_dir is None:
        return False
    meta = _read_meta(Path(root_dir))
    return bool(
        meta
        and meta.get("provider") == PROVIDER
        and meta.get("signature") == PROVIDER
        and meta.get("lightrag_adapter_schema") == ADAPTER_SCHEMA
        and meta.get("parser_bridge_schema") == 1
        and meta.get("state") == PUBLISHED_STATE
        and has_output(Path(root_dir))
    )


def _parser_inputs(root_dir: Path) -> list[dict[str, str]]:
    from .ingress import bundles_root, load_verified_bundle

    records: set[tuple[str, str]] = set()
    for bundle in sorted(bundles_root(root_dir).glob("*.bundle")):
        canonical_name = bundle.name.removesuffix(".bundle")
        manifest, _ = load_verified_bundle(root_dir, canonical_name)
        parser = manifest.get("parser")
        if not isinstance(parser, dict):
            continue
        records.add(
            (
                str(parser.get("engine") or ""),
                str(parser.get("parser_signature") or ""),
            )
        )
    return [
        {"engine": engine, "parser_signature": signature} for engine, signature in sorted(records)
    ]


def read_published_policy(root_dir: Path | None) -> dict[str, Any] | None:
    if root_dir is None or not meta_is_native_published(root_dir):
        return None
    meta = _read_meta(Path(root_dir)) or {}
    policy = meta.get("indexing_policy")
    if isinstance(policy, dict):
        return policy
    return {"policy": "legacy_unpinned"}


def embedding_matches(root_dir: Path, signature: EmbeddingSignature | None) -> bool:
    """Compare the published vector identity, never just its dimension."""
    meta = _read_meta(root_dir) or {}
    return signature is not None and meta.get("embedding_signature") == signature.signature()


def require_compatible_embedding(root_dir: Path, config: EmbeddingConfig) -> None:
    """Reject reads and appends when the published embedding identity differs."""
    def signature_from_config(config): return config

    from .indexing_policy import EmbeddingMismatchError

    if not embedding_matches(root_dir, signature_from_config(config)):
        raise EmbeddingMismatchError(
            "The current embedding configuration does not match this LightRAG index. "
            "Restore the original embedding configuration or rebuild with the current embedding "
            "before querying or adding documents."
        )


def write_meta(
    root_dir: Path,
    *,
    indexing_policy: dict[str, Any] | None = None,
    embedding_config: EmbeddingConfig | None = None,
    state: str = PUBLISHED_STATE,
) -> None:
    """Write a flat-layout ``meta.json`` so the version lists as ready.

    Mirrors ``index_versioning.write_version_meta`` but carries a synthetic
    ``lightrag`` signature instead of an embedding hash. The embedding identity
    is stamped alongside so an externally-linked index can be checked for
    embedding compatibility at connect time (LightRAG otherwise fails retrieval
    silently on a dimension mismatch).
    """
    from .engine import installed_version, workspace_for
    if embedding_config is None: raise ValueError("写入元信息需要固定嵌入配置")
    target=Path(root_dir)
    previous=_read_meta(target) or {}
    now=datetime.now(timezone.utc).replace(tzinfo=None).isoformat()+"Z"
    embedding_fields={"embedding_signature":embedding_config.signature(),
                      "embedding_model":embedding_config.model,"embedding_dim":embedding_config.dim}
    payload = {
        "version": target.name,
        "signature": PROVIDER,
        "provider": PROVIDER,
        "state": state,
        "lightrag_adapter_schema": ADAPTER_SCHEMA,
        "lightrag_package_version": installed_version(),
        "parser_bridge_schema": 1,
        "parser_inputs": _parser_inputs(target),
        "workspace": workspace_for(target),
        "layout": "flat",
        "created_at": str(previous.get("created_at") or now),
        "updated_at": now,
        "indexing_policy": indexing_policy
        or previous.get("indexing_policy")
        or {"policy": "legacy_unpinned"},
        **embedding_fields,
    }
    atomic_write_json(target / META_FILENAME, payload)


__all__ = [
    "META_FILENAME",
    "PROVIDER",
    "document_error",
    "failure_summary",
    "has_any_doc_status",
    "working_dir",
    "has_output",
    "meta_is_native_published",
    "read_published_policy",
    "write_meta",
]
