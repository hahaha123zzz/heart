"""数据库连接与会话管理。

【自主衔接】"存储层"入口之一：只负责 engine / Session / 建表，不含业务逻辑。
换数据库只改 .env 里的 DATABASE_URL：
    MySQL:      mysql+pymysql://ai_tutor:<pw>@127.0.0.1:3306/ai_tutor
    SQLite:     sqlite:///./ai_tutor.db
    PostgreSQL: postgresql+psycopg://user:pw@127.0.0.1:5432/ai_tutor
"""

from __future__ import annotations

import os
import datetime as dt
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, text
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
    """只做增量建表/加列；绝不清理已有学生数据。"""
    from database import models  # noqa: F401  确保模型已注册

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    columns = {item["name"] for item in inspector.get_columns("conversations")} if "conversations" in tables else set()
    migration_needed = "students" in tables and (bool(set(models.Base.metadata.tables) - tables) or "turn_id" not in columns)
    if migration_needed and engine.dialect.name == "sqlite":
        source = Path(engine.url.database).resolve()
        backup_dir = Path(os.getenv("DATABASE_BACKUP_DIR") or Path(__file__).resolve().parents[1] / "backups").resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"before-accounts-{dt.datetime.utcnow():%Y%m%d-%H%M%S-%f}.sqlite3"
        with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(target)) as backup:
            original.backup(backup)
    elif migration_needed and os.getenv("ALLOW_EXISTING_DB_MIGRATION") != "1":
        raise RuntimeError("现有非 SQLite 数据库需要先完整备份；完成后设置 ALLOW_EXISTING_DB_MIGRATION=1 再启动。")
    models.Base.metadata.create_all(engine)
    if "turn_id" not in {item["name"] for item in inspect(engine).get_columns("conversations")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN turn_id VARCHAR(36)"))
    if "ix_conversations_turn_id" not in {item["name"] for item in inspect(engine).get_indexes("conversations")}:
        next(index for index in models.ConversationRow.__table__.indexes if index.name == "ix_conversations_turn_id").create(bind=engine)


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
