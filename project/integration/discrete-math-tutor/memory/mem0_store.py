"""mem0 卡片索引适配层。

只做存储与检索：infer=False，卡片内容与 metadata 由宿主决定。
"""
from __future__ import annotations

import os

os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def _patch_fastembed() -> None:
    """让 mem0 的 fastembed provider 使用项目已缓存的 ONNX 快照。"""
    import mem0.embeddings.fastembed as module
    from fastembed import TextEmbedding

    snapshot = os.environ.get("LIGHTRAG_EMBED_SNAPSHOT")
    if not snapshot or getattr(module, "_heart_patched", False):
        return

    def factory(model_name=None, **kwargs):
        return TextEmbedding(
            model_name=model_name or "BAAI/bge-small-zh-v1.5",
            specific_model_path=snapshot,
            **kwargs,
        )

    module.TextEmbedding = factory
    module._heart_patched = True


def enabled() -> bool:
    return os.getenv("MEM0_ENABLED", "0") == "1"


def _config() -> dict:
    connection = os.environ["COURSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    return {
        "history_db_path": os.getenv("MEM0_HISTORY_PATH", ".runtime/mem0/history.sqlite"),
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "connection_string": connection,
                "collection_name": "student_memory",
                "embedding_model_dims": 512,
                "hnsw": True,
            },
        },
        "embedder": {
            "provider": "fastembed",
            "config": {"model": "BAAI/bge-small-zh-v1.5", "embedding_dims": 512},
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": os.getenv("OPENAI_MODEL", "deepseek-flash"),
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
            },
        },
    }


class Mem0Store:
    def __init__(self, enabled: bool | None = None):
        self.enabled = enabled if enabled is not None else _enabled_default()
        self._memory = None
        if self.enabled:
            parent = os.path.dirname(os.path.abspath(os.getenv("MEM0_HISTORY_PATH", ".runtime/mem0/history.sqlite")))
            os.makedirs(parent, exist_ok=True)
            _patch_fastembed()
            from mem0 import Memory

            self._memory = Memory.from_config(_config())

    def add_card(self, student_id: str, card: dict) -> str:
        if self._memory is None:
            return ""
        metadata = {
            "card_id": int(card["card_id"]),
            "student_id": student_id,
            "source_kind": card.get("source_kind", ""),
            "source_id": card.get("source_id", ""),
            "verification": card.get("verification", ""),
            "epoch": int(card.get("epoch") or 0),
        }
        result = self._memory.add(
            [{"role": "user", "content": card["content"]}],
            user_id=student_id,
            metadata=metadata,
            infer=False,
        )
        rows = result.get("results") if isinstance(result, dict) else None
        return str(rows[0].get("id") or "") if rows else ""

    def search(self, student_id: str, query: str, epoch: int | None = None, limit: int = 20) -> list[dict]:
        if self._memory is None:
            return []
        filters = {"user_id": student_id}
        if epoch is not None:
            filters["epoch"] = int(epoch)
        result = self._memory.search(
            query,
            filters=filters,
            top_k=limit,
            threshold=0.1,
        )
        rows = result.get("results") if isinstance(result, dict) else None
        hits = []
        for row in rows or []:
            card_id = (row.get("metadata") or {}).get("card_id")
            if card_id is None:
                continue
            hits.append({"memory_id": str(row.get("id") or ""), "card_id": int(card_id)})
        return hits

    def delete(self, memory_id: str) -> None:
        if self._memory is not None and memory_id:
            self._memory.delete(memory_id)

    def close(self) -> None:
        self._memory = None


def _enabled_default() -> bool:
    return enabled()
