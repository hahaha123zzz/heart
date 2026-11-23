"""记忆卡片在 PostgreSQL 上的中文全文检索。"""
import importlib
import os

from tests.pg_support import temp_databases


def test_chinese_bigram_search_hits_card():
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["TUTOR_COURSE"] = "experimental-psychology-3"
        import database.database as db

        importlib.reload(db)
        db.init_db()
        from database.models import MemoryDocumentRow, Student
        from database.memory_index import MemoryIndexRepository, memory_terms

        with db.session_scope() as session:
            session.add(Student(student_id="s"))
            session.flush()
            session.add(
                MemoryDocumentRow(
                    student_id="s",
                    source_kind="conversation",
                    source_id="1",
                    knowledge_point="自变量",
                    content="学生分不清自变量和额外变量",
                    index_text=" ".join(sorted(memory_terms("自变量 学生分不清自变量和额外变量"))),
                    content_hash="h",
                    source_metadata={},
                    embedding=[],
                    embedding_model="",
                )
            )
        ids, mode = MemoryIndexRepository().memory_lexical("s", "自变量是什么")
        assert mode == "postgres_tsvector" and ids
