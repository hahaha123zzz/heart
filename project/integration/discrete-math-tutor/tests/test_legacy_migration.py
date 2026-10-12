"""模拟旧 SQLite 库，检查首次迁移先备份且不删除旧学生。"""

import os
import sqlite3
from contextlib import closing
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix="dm-legacy-test-") as temp:
        db_path = Path(temp) / "legacy.db"
        backup_dir = Path(temp) / "backups"
        with closing(sqlite3.connect(db_path)) as conn:
            conn.executescript("""
                CREATE TABLE students (student_id VARCHAR(64) PRIMARY KEY,
                    account_type VARCHAR(20), created_at DATETIME, expires_at DATETIME);
                CREATE TABLE conversations (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id VARCHAR(64), role VARCHAR(16), content TEXT, created_at DATETIME);
                INSERT INTO students VALUES ('old-test', 'test', CURRENT_TIMESTAMP, '2020-01-01');
                INSERT INTO conversations (student_id, role, content, created_at)
                    VALUES ('old-test', 'user', '旧问题', CURRENT_TIMESTAMP);
            """)
        os.environ["DATABASE_URL"] = "sqlite:///" + db_path.as_posix()
        os.environ["DATABASE_BACKUP_DIR"] = str(backup_dir)
        from database.database import engine, init_db
        try:
            init_db()
            backups = list(backup_dir.glob("before-accounts-*.sqlite3"))
            assert len(backups) == 1, backups
            with closing(sqlite3.connect(backups[0])) as conn:
                assert conn.execute("SELECT content FROM conversations").fetchone()[0] == "旧问题"
                assert "turn_id" not in [row[1] for row in conn.execute("PRAGMA table_info(conversations)")]
            with closing(sqlite3.connect(db_path)) as conn:
                assert conn.execute("SELECT student_id FROM students").fetchone()[0] == "old-test"
                assert conn.execute("SELECT content FROM conversations").fetchone()[0] == "旧问题"
                assert "turn_id" in [row[1] for row in conn.execute("PRAGMA table_info(conversations)")]
                assert "users" in [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            init_db()
            assert len(list(backup_dir.glob("before-accounts-*.sqlite3"))) == 1
            print("旧库自动备份与无损增量迁移：通过")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
