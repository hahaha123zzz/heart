"""数据库连接与会话管理。

【自主衔接】"存储层"入口之一：只负责 engine / Session / 建表，不含业务逻辑。
换数据库只改 .env 里的 DATABASE_URL：
    MySQL:      mysql+pymysql://ai_tutor:<pw>@127.0.0.1:3306/ai_tutor
    SQLite:     sqlite:///./ai_tutor.db
    PostgreSQL: postgresql+psycopg://user:pw@127.0.0.1:5432/ai_tutor
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_URL = "sqlite:///./ai_tutor.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_URL)

_engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, future=True, **_engine_kwargs)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True
)

if DATABASE_URL.startswith("sqlite"):
    # SQLite 默认不强制外键，需逐连接开启，才能让 ON DELETE CASCADE 生效
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    """建表（幂等）。"""
    from database import models  # noqa: F401  确保模型已注册

    models.Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """一次请求一个事务；异常自动回滚。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
