"""本机 PostgreSQL + mem0 验收：库、扩展、计数、增删查。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import psycopg


def _url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://")


def main() -> None:
    from memory.mem0_store import Mem0Store

    report = {"databases": {}, "vector": None, "memory": {}}
    for name, key in (("business", "DATABASE_URL"), ("course", "COURSE_DATABASE_URL")):
        with psycopg.connect(_url(os.environ[key])) as conn:
            report["databases"][name] = conn.execute("select current_database()").fetchone()[0]
    with psycopg.connect(_url(os.environ["COURSE_DATABASE_URL"])) as conn:
        report["vector"] = conn.execute(
            "select extversion from pg_extension where extname='vector'").fetchone()[0]
        report["students"] = conn.execute("select count(*) from students").fetchone()[0]
    from knowledge.lightrag import storage

    with storage._pg_connect() as conn:
        report["databases"]["rag"] = conn.info.dbname
        report["lightrag_docs"] = conn.execute("select count(*) from lightrag_doc_status").fetchone()[0]
        report["lightrag_chunks"] = conn.execute("select count(*) from lightrag_doc_chunks").fetchone()[0]
    store = Mem0Store(enabled=True)
    user = "accept-" + uuid4().hex[:8]
    memory_id = store.add_card(user, {"card_id": 1, "content": "验收：自变量与额外变量的区别",
                                      "source_kind": "conversation", "source_id": "accept", "epoch": 1})
    hits = store.search(user, "自变量和额外变量", limit=5)
    store.delete(memory_id)
    report["memory"] = {"add": bool(memory_id), "search": any(h["memory_id"] == memory_id for h in hits),
                        "delete": memory_id not in [h["memory_id"] for h in store.search(user, "自变量", limit=5)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(report["memory"].values()) else 1)


if __name__ == "__main__":
    main()
