"""幂等初始化学生测试账号。

明文密码只写入 `.runtime/student-accounts.txt`（不提交、不进日志）；重复运行不会
重置已有密码，也不会重复列出账号。
"""
from __future__ import annotations

import secrets
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_api import create_account
from database.database import init_db

COUNT = 10
OUT = Path(".runtime") / "student-accounts.txt"


def main() -> None:
    init_db()
    created = []
    for index in range(1, COUNT + 1):
        student_id = f"student{index:02d}"
        password = secrets.token_urlsafe(9)
        if create_account(student_id, password):
            created.append((student_id, password))
    if created:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as handle:
            handle.write(f"# {datetime.now().isoformat(timespec='seconds')}\n")
            for student_id, password in created:
                handle.write(f"{student_id}\t{password}\n")
    print(f"created={len(created)} skipped={COUNT - len(created)} file={OUT}")


if __name__ == "__main__":
    main()
