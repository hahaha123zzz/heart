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
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@contextlib.contextmanager
def temp_databases(prefix: str = "heart_test") -> Iterator[dict]:
    base = _split(maintenance_url())
    suffix = uuid.uuid4().hex[:10]
    business = f"{prefix}_{suffix}"
    course = f"{prefix}_course_{suffix}"
    rag = f"{prefix}_rag_{suffix}"
    names = [business, course, rag]
    _create(maintenance_url(), names)
    env = {
        "DATABASE_URL": _sqlalchemy_url(base, business),
        "COURSE_DATABASE_URL": _sqlalchemy_url(base, course),
        "POSTGRES_DATABASE": rag,
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
