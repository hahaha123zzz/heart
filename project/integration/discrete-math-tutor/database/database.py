"""数据库连接与会话管理。

【自主衔接】"存储层"入口之一：只负责 engine / Session / 建表，不含业务逻辑。
换数据库只改 .env 里的 DATABASE_URL：
    MySQL:      mysql+pymysql://ai_tutor:<pw>@127.0.0.1:3306/ai_tutor
    SQLite:     sqlite:///./ai_tutor.db
    PostgreSQL: postgresql+psycopg://user:pw@127.0.0.1:5432/ai_tutor

心理学模式的SQLite采用独立课程文件；COURSE_DATABASE_URL可显式指定独立库。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import make_url
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_URL = "sqlite:///./ai_tutor.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_URL)

def course_database_url(url):
    from knowledge.course_config import PSYCHOLOGY
    if not PSYCHOLOGY:return url
    original=make_url(url)
    explicit=os.getenv('COURSE_DATABASE_URL')
    if explicit:
        candidate=make_url(explicit)
        same=candidate==original
        if candidate.get_backend_name()=='sqlite' and original.get_backend_name()=='sqlite':
            same=Path(candidate.database or '').resolve()==Path(original.database or '').resolve()
        if same:raise ValueError('心理学学习数据库必须与旧课程数据库分开')
        return explicit
    if original.get_backend_name()!='sqlite':
        raise ValueError('请用COURSE_DATABASE_URL指定心理学课程独立数据库')
    if original.database==':memory:':return url
    path=Path(original.database or 'ai_tutor.db')
    target=path.with_name(path.stem+'.experimental-psychology-3'+path.suffix)
    return original.set(database=str(target)).render_as_string(hide_password=False)

DATABASE_URL=course_database_url(DATABASE_URL)

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


_current_session: ContextVar[Session | None] = ContextVar("memory_session", default=None)


def init_db() -> None:
    """建表（幂等）。"""
    from database import models  # noqa: F401  确保模型已注册
    from database import q5_learning  # noqa: F401  Q5 首批路径表

    models.Base.metadata.create_all(engine)
    from database.conversation_session_migration import migrate_conversation_sessions
    migrate_conversation_sessions(engine)


@contextmanager
def session_scope(*, immediate: bool = False) -> Iterator[Session]:
    """复用外层工作单元，短事务提交；SQLite 写入可先取得写锁。"""
    current = _current_session.get()
    if current is not None:
        yield current
        return
    session = SessionLocal()
    token = _current_session.set(session)
    try:
        if immediate and session.bind.dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _current_session.reset(token)
        session.close()
