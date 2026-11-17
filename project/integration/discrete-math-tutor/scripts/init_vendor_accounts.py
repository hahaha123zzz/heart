"""幂等创建厂家用户：1 个管理员 + 10 个学生（学生不因“首个用户”被提权）。

明文密码只写 `.runtime/vendor-accounts.txt`（gitignored）。
"""
from __future__ import annotations

import secrets
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"E:\项目\heart\project\vendor\DeepTutor")

from deeptutor.services.auth import _load_users, add_user  # noqa: E402
from deeptutor.multi_user import identity  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / ".runtime" / "vendor-accounts.txt"


def ensure(username: str, role: str, preset: str) -> tuple[str, str] | None:
    if username in _load_users():
        return None
    password = secrets.token_urlsafe(9)
    add_user(username, password, role=role, preset=preset)
    return username, password


def main() -> None:
    created = [c for c in (ensure("admin", "admin", "standard"),) if c]
    for index in range(1, 11):
        item = ensure(f"student{index:02d}", "user", "learner")
        if item:
            created.append(item)
    if created or OUT.is_file():
        OUT.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, str] = {}
        if OUT.is_file():
            for line in OUT.read_text(encoding="utf-8").splitlines():
                if "\t" in line and not line.startswith("#"):
                    name, secret = line.split("\t", 1)
                    existing[name] = secret
        for username, password in created:
            existing[username] = password
        if existing:
            body = "".join(f"{name}\t{secret}\n" for name, secret in sorted(existing.items()))
            OUT.write_text(f"# {datetime.now().isoformat(timespec='seconds')}\n{body}", encoding="utf-8")
    print(f"created={len(created)} users={len(_load_users())} file={OUT}")
    print(f"users_store={identity.USERS_FILE}")


if __name__ == "__main__":
    main()
