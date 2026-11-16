"""mem0 适配层：真实 pgvector 增删查。"""
import os

from tests.pg_support import temp_databases


def test_add_search_delete(tmp_path):
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["MEM0_HISTORY_PATH"] = str(tmp_path / "history.sqlite")
        from memory.mem0_store import Mem0Store

        store = Mem0Store(enabled=True)
        memory_id = store.add_card("s1", {
            "card_id": 7,
            "content": "学生分不清自变量和额外变量",
            "source_kind": "conversation",
            "source_id": "c1",
            "verification": "student_statement",
            "epoch": 1,
        })
        assert memory_id
        hits = store.search("s1", "自变量和额外变量", epoch=1, limit=5)
        assert {"memory_id": memory_id, "card_id": 7} in hits
        store.delete(memory_id)
        assert memory_id not in [hit["memory_id"] for hit in store.search("s1", "自变量", epoch=1)]
