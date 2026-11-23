"""检索优先走 mem0，PG 关键词始终兜底。"""
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from database import database as db
from tests.pg_support import temp_engine


class FakeStore:
    def __init__(self, card_id):
        self.card_id = card_id
        self.queries = []

    def search(self, student_id, query, epoch=None, limit=20):
        self.queries.append((student_id, query))
        return [{"memory_id": "m1", "card_id": self.card_id}]


def test_dense_uses_mem0_and_reports_status():
    with temp_engine() as engine:
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with patch.object(db, "SessionLocal", factory):
            from memory.memory_manager import MemoryManager
            from memory.retrieval import MemoryRetriever

            memory = MemoryManager()
            memory.ensure_student("s")
            memory.append("s", "user", "我总是把集合元素和单元素集合混淆")
            from database.models import ConversationRow, LearningEventRow

            with db.session_scope() as session:
                conv = session.query(ConversationRow).filter_by(student_id="s").one()
                session.add(LearningEventRow(id="e1", student_id="s", source_key="e1", knowledge_point="集合",
                    event_type="chat_turn", status="committed",
                    payload={"conversation_ids": [conv.id], "content": conv.content}))
            memory.repo.sync_memory_index("s")
            docs = memory.repo.memory_documents("s")
            assert docs
            store = FakeStore(docs[0]["id"])
            context = MemoryRetriever(memory, mem0_store=store).retrieve("s", question="集合元素混淆")
            assert context["retrieval"]["dense"] == "mem0"
            assert any("单元素" in item["content"] for item in context["items"])
            assert store.queries


def test_lexical_fallback_without_mem0():
    with temp_engine() as engine:
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with patch.object(db, "SessionLocal", factory), patch("memory.retrieval._model", return_value=(None, None)):
            from memory.memory_manager import MemoryManager
            from memory.retrieval import MemoryRetriever

            memory = MemoryManager()
            memory.ensure_student("s")
            memory.append("s", "user", "我总是把集合元素和单元素集合混淆")
            with patch.dict("os.environ", {"MEM0_ENABLED": "0"}):
                context = MemoryRetriever(memory).retrieve("s", question="集合元素混淆")
            assert any("单元素" in item["content"] for item in context["items"])
