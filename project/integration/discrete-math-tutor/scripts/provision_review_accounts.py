"""部署前离线初始化固定的十个永久评审账号，凭据仅存指定 worker 的本地运行目录。"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import secrets
import subprocess
import sys

HOST = Path(__file__).resolve().parents[1]
VENDOR = HOST.parents[1] / "vendor" / "DeepTutor"
NAMES = tuple(f"heart-review-{i:02d}" for i in range(1, 11))


def _private_directory(path: Path) -> None:
    # Windows chmod 无法收紧 ACL，先保护目录再创建含密码的文件。
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True, encoding="oem")
        sid = next(csv.reader([identity.strip()]))[-1]
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                       check=True, capture_output=True)
    else:
        path.chmod(0o700)


def occupied_host_names(names):
    if not names:
        return set()
    from sqlalchemy import inspect, or_, select, text
    from database.database import engine
    from database.models import (Student, AuthAccountRow, StudentModelCredential, StudentModelCheck,
        StudentMemorySetting, AssessmentQueueSetting, AssessmentJobRow)
    with engine.begin() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        inspector = inspect(connection)
        occupied = set()
        for model in (Student, AuthAccountRow, StudentModelCredential, StudentModelCheck,
                      StudentMemorySetting, AssessmentQueueSetting, AssessmentJobRow):
            if inspector.has_table(model.__tablename__):
                matches = model.student_id.in_(names)
                if model is AuthAccountRow:
                    matches = or_(matches, model.username.in_(names))
                    occupied.update(connection.scalars(select(model.username).where(model.username.in_(names))))
                occupied.update(connection.scalars(select(model.student_id).where(matches)))
    return occupied


def read_credentials(output: Path):
    credentials = {}
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            name, sep, password = line.partition("\t")
            if not sep or name in credentials or name not in NAMES or len(password) < 32:
                raise ValueError("已有凭据文件格式无效，未修改账号。")
            credentials[name] = password
        if set(credentials) != set(NAMES):
            raise ValueError("已有凭据文件不完整，未修改账号。")
    return credentials


def provision(home: Path):
    from filelock import FileLock
    from deeptutor.multi_user import identity
    from deeptutor.services import auth
    from deeptutor.services.file_io import atomic_write_text

    if not identity.USERS_FILE.resolve().is_relative_to(home):
        raise ValueError("厂家身份存储不在指定工作目录内。")
    if not auth.AUTH_ENABLED or auth.POCKETBASE_ENABLED:
        raise ValueError("请在目标目录启用厂家本地认证，再初始化评审账号。")
    folder = home / ".runtime" / "review-accounts"
    if folder.resolve() != folder:
        raise ValueError("凭据目录不能通过符号链接或目录联接指向别处。")
    _private_directory(folder)
    output = folder / "vendor-accounts.txt"
    with FileLock(str(folder / "provision.lock"), timeout=0):
        if output.resolve() != output:
            raise ValueError("凭据文件不能指向别处。")
        credentials = read_credentials(output)
        users = auth._load_users()
        if not any(u.get("role") == "admin" and not u.get("disabled") for u in users.values()):
            raise ValueError("目标目录须先有一个可用管理员。")
        for name in NAMES:
            existing = users.get(name)
            if existing and (name not in credentials or existing.get("role") != "user"
                             or existing.get("preset") != "learner" or existing.get("disabled")
                             or not auth.verify_password(credentials[name], existing["hash"])):
                raise ValueError(f"账号 {name} 已占用或身份不匹配，未修改账号。")
        missing = [name for name in NAMES if name not in users]
        occupied = occupied_host_names(missing)
        if occupied:
            raise ValueError(f"H 中已有同名数据，未修改账号：{', '.join(sorted(occupied))}")
        if not credentials:
            credentials = {name: secrets.token_urlsafe(32) for name in NAMES}
            # 先持久化预留密码。中断后可用同一批密码补齐，避免已有账号无法交付。
            atomic_write_text(output, "".join(f"{name}\t{credentials[name]}\n" for name in NAMES))
        for name in missing:
            auth.add_user(name, credentials[name], role="user", preset="learner")
        return len(missing), output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True, help="已启用本地认证、且 worker 已停止的目标目录")
    args = parser.parse_args()
    home = args.home.resolve(strict=True)
    os.environ["DEEPTUTOR_HOME"] = str(home)
    sys.path[:0] = [str(HOST), str(VENDOR)]
    created, output = provision(home)
    print(f"已创建 {created} 个账号，共 {len(NAMES)} 个。凭据文件：{output}")


if __name__ == "__main__":
    main()
