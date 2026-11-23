"""宿主数据库只支持 PostgreSQL。"""
import importlib
import os

import pytest

from tests.pg_support import temp_databases


def test_session_scope_immediate_serializes_writers():
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["TUTOR_COURSE"] = "experimental-psychology-3"
        import database.database as db

        importlib.reload(db)
        assert db.DATABASE_URL.startswith("postgresql+psycopg://")
        db.init_db()
        with db.session_scope(immediate=True) as session:
            assert session.bind.dialect.name == "postgresql"
            assert session.execute(db.text("select 1")).scalar() == 1


def test_course_database_must_differ():
    with temp_databases() as env:
        same = env["COURSE_DATABASE_URL"]
        os.environ.update(env)
        os.environ["TUTOR_COURSE"] = "experimental-psychology-3"
        os.environ["COURSE_DATABASE_URL"] = same
        import database.database as db

        importlib.reload(db)
        with pytest.raises(ValueError):
            db.course_database_url(same)
