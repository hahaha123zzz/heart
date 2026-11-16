"""临时 PostgreSQL 测试库。

每个测试用独立的业务库和 LightRAG 库，结束后删除；不得复用开发库。
维护库连接读 TEST_POSTGRES_URL，默认指向本机 postgres 库。
"""
from __future__ import annotations

import contextlib
import os
from typing import Iterator
from urllib.parse import quote, urlsplit
import uuid

import psycopg

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_URL = "postgresql://heart@127.0.0.1:5432/postgres"


def maintenance_url() -> str:
    return os.environ.get("TEST_POSTGRES_URL", DEFAULT_URL)


def admin_url() -> str:
    return os.environ.get("TEST_POSTGRES_ADMIN_URL", maintenance_url())


def _psycopg_url(base, database: str) -> str:
    user = quote(base.username or "", safe="")
    password = quote(base.password or "", safe="")
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql://{auth}{base.hostname}:{base.port or 5432}/{database}"


def _ensure_extensions(names: list[str]) -> None:
    base = _split(admin_url())
    for name in names:
        with psycopg.connect(_psycopg_url(base, name), autocommit=True) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")


def _split(url: str):
    return urlsplit(url)


def _sqlalchemy_url(base, database: str) -> str:
    user = quote(base.username or "", safe="")
    password = quote(base.password or "", safe="")
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql+psycopg://{auth}{base.hostname}:{base.port or 5432}/{database}"


def _create(url: str, names: list[str]) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        for name in names:
            conn.execute(f'CREATE DATABASE "{name}"')


def _drop(url: str, names: list[str]) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        for name in names:
            try:
                conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            except psycopg.Error:
                # shortcut: 后台线程/子进程仍持有连接时 FORCE 可能无权终止；
                # 清理失败只留下唯一命名的测试库，不影响后续用例，升级为专用测试实例时再严格处理。
                conn.rollback()


@contextlib.contextmanager
def temp_databases(prefix: str = "heart_test") -> Iterator[dict]:
    base = _split(maintenance_url())
    suffix = uuid.uuid4().hex[:10]
    business = f"{prefix}_{suffix}"
    course = f"{prefix}_course_{suffix}"
    rag = f"{prefix}_rag_{suffix}"
    names = [business, course, rag]
    _create(maintenance_url(), names)
    _ensure_extensions(names)
    env = {
        "DATABASE_URL": _sqlalchemy_url(base, business),
        "COURSE_DATABASE_URL": _sqlalchemy_url(base, course),
        "POSTGRES_DATABASE": rag,
        "POSTGRES_DATABASE_URL": _sqlalchemy_url(base, rag),
        "POSTGRES_HOST": base.hostname or "127.0.0.1",
        "POSTGRES_PORT": str(base.port or 5432),
        "POSTGRES_USER": base.username or "",
        "POSTGRES_PASSWORD": base.password or "",
        "TEST_POSTGRES_URL": maintenance_url(),
    }
    try:
        yield env
    finally:
        _drop(maintenance_url(), names)


@contextlib.contextmanager
def temp_engine(create_all: bool = True) -> Iterator[object]:
    """临时 PostgreSQL 引擎；用于替换测试里的内存 SQLite。"""
    from sqlalchemy import create_engine

    with temp_databases() as env:
        os.environ.update(env)
        os.environ["MEM0_ENABLED"] = "0"
        engine = create_engine(env["COURSE_DATABASE_URL"], future=True)
        try:
            if create_all:
                import database.q5_learning  # noqa: F401  与 init_db 一致，登记 Q5 表
                from database.models import Base

                Base.metadata.create_all(engine)
            yield engine
        finally:
            engine.dispose()
