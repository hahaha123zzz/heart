"""删除/epoch 让卡片失效。"""
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from database import database as db
from tests.pg_support import temp_engine


def test_expire_cards_hides_old_epoch():
    with temp_engine() as engine:
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with patch.object(db, "SessionLocal", factory):
            from database.models import MemoryDocumentRow, Student

            with db.session_scope() as session:
                session.add(Student(student_id="s"))
                session.flush()
                session.add(MemoryDocumentRow(
                    student_id="s", source_kind="conversation", source_id="c1",
                    knowledge_point="集合", content="旧记忆", index_text="集合 旧记忆",
                    content_hash="h", source_metadata={"epoch": 0}, embedding=[], embedding_model="",
                ))
            from database.memory_index import MemoryIndexRepository

            repo = MemoryIndexRepository()
            assert repo.memory_documents("s")
            assert repo.expire_cards("s", "集合", 1) == 1
            assert repo.memory_documents("s") == []
