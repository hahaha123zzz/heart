"""临时 PostgreSQL 测试库夹具的自测。"""
import psycopg

from tests.pg_support import maintenance_url, temp_databases


def test_temp_databases_are_isolated():
    from urllib.parse import urlsplit

    with temp_databases() as env:
        names = [urlsplit(env[key]).path.lstrip("/") for key in ("DATABASE_URL", "COURSE_DATABASE_URL")]
        assert all(name.startswith("heart_test_") for name in names)
        with psycopg.connect(env["COURSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")) as conn:
            assert conn.execute("select current_database()").fetchone()[0].startswith("heart_test_")
    with psycopg.connect(maintenance_url()) as conn:
        remaining = [name for name in names
                     if conn.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()]
    assert not remaining
