"""卡片异步同步到 mem0：幂等、停用后删除。"""
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from database import database as db
from tests.pg_support import temp_engine


class FakeStore:
    def __init__(self):
        self.added = []
        self.deleted = []

    def add_card(self, student_id, card):
        self.added.append((student_id, card))
        return "m-" + str(card["card_id"])

    def delete(self, memory_id):
        self.deleted.append(memory_id)


def test_indexer_adds_once_then_deletes_inactive(tmp_path):
    with temp_engine() as engine:
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        from database.models import MemoryDocumentRow, Student

        with patch.object(db, "SessionLocal", factory), patch.object(db, "engine", engine):
            with db.session_scope() as session:
                session.add(Student(student_id="s"))
                session.flush()
                session.add(MemoryDocumentRow(
                    student_id="s", source_kind="conversation", source_id="c1",
                    knowledge_point="自变量", content="学生分不清自变量和额外变量",
                    index_text="自变量", content_hash="h1",
                    source_metadata={"verification": "student_statement", "epoch": 1},
                    embedding=[], embedding_model="",
                ))
            from memory.mem0_indexer import Mem0Indexer

            store = FakeStore()
            indexer = Mem0Indexer(SimpleNamespace(), store)
            assert indexer.run_once() is True
            assert len(store.added) == 1
            assert store.added[0][1]["card_id"]
            with db.session_scope() as session:
                row = session.query(MemoryDocumentRow).one()
                assert row.mem0_id == "m-" + str(row.id)
            assert indexer.run_once() is False
            with db.session_scope() as session:
                session.query(MemoryDocumentRow).one().active = False
            assert indexer.run_once() is True
            assert store.deleted == ["m-1"]
