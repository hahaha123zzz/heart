"""临时 PostgreSQL 测试库夹具的自测。"""
import psycopg

from tests.pg_support import maintenance_url, temp_databases


def test_temp_databases_are_isolated():
    with temp_databases() as env:
        assert "heart_test_" in env["COURSE_DATABASE_URL"]
        assert "heart_test_" in env["DATABASE_URL"]
        with psycopg.connect(env["COURSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")) as conn:
            assert conn.execute("select current_database()").fetchone()[0].startswith("heart_test_")
    with psycopg.connect(maintenance_url()) as conn:
        names = [r[0] for r in conn.execute("select datname from pg_database where datname like 'heart_test_%'")]
    assert not names
