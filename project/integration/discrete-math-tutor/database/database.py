"""数据库连接与会话管理。

【自主衔接】"存储层"入口之一：只负责 engine / Session / 建表，不含业务逻辑。
只支持 PostgreSQL，连接串写在 .env 的 DATABASE_URL / COURSE_DATABASE_URL：
    postgresql+psycopg://heart:<pw>@127.0.0.1:5432/heart
心理学模式必须用 COURSE_DATABASE_URL 指定独立课程库。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import make_url

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_URL = "postgresql+psycopg://heart@127.0.0.1:5432/heart"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_URL)


def course_database_url(url):
    from knowledge.course_config import PSYCHOLOGY

    if not PSYCHOLOGY:
        return url
    original = make_url(url)
    explicit = os.getenv("COURSE_DATABASE_URL")
    if not explicit:
        raise ValueError("请用COURSE_DATABASE_URL指定心理学课程独立数据库")
    if make_url(explicit) == original:
        raise ValueError("心理学学习数据库必须与旧课程数据库分开")
    return explicit


DATABASE_URL = course_database_url(DATABASE_URL)
if make_url(DATABASE_URL).get_backend_name() != "postgresql":
    raise ValueError("只支持 PostgreSQL 数据库")

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True
)

_current_session: ContextVar[Session | None] = ContextVar("memory_session", default=None)


def init_db() -> None:
    """建表（幂等）。"""
    from database import models  # noqa: F401  确保模型已注册
    from database import q5_learning  # noqa: F401  Q5 首批路径表

    models.Base.metadata.create_all(engine)
    from database.conversation_session_migration import migrate_conversation_sessions

    migrate_conversation_sessions(engine)
    from database.preference_value_migration import migrate_preference_values

    migrate_preference_values(engine)
    from database.memory_index import ensure_search_index

    ensure_search_index(engine)


@contextmanager
def session_scope(*, immediate: bool = False) -> Iterator[Session]:
    """复用外层工作单元，短事务提交；PostgreSQL 用事务级咨询锁串行化写入。"""
    current = _current_session.get()
    if current is not None:
        yield current
        return
    session = SessionLocal()
    token = _current_session.set(session)
    try:
        if immediate and session.bind.dialect.name == "postgresql":
            # shortcut: 单库级 advisory lock 复刻 SQLite 单写者语义；
            # 多用户高并发写入成为瓶颈时改为按 student_id 哈希的细粒度锁。
            session.execute(text("SELECT pg_advisory_xact_lock(2147480001)"))
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _current_session.reset(token)
        session.close()
