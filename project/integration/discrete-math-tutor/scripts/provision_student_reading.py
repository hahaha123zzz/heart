"""为每个学生账号导入固定教材并写进其 learning_policy。

厂家阅读材料按用户隔离，所以只能逐账号上传（幂等：库里已有同名材料就复用）。
用法：python scripts/provision_student_reading.py [--base http://127.0.0.1:3000]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".." / ".." / "vendor" / "DeepTutor"))

from deeptutor.multi_user.grants import empty_grant, load_grant, save_grant  # noqa: E402
from deeptutor.multi_user.identity import get_user  # noqa: E402

CREDS = ROOT / ".runtime" / "vendor-accounts.txt"
TEXTBOOK = ROOT / "knowledge" / "courses" / "experimental-psychology-3" / "source" / "textbook.docx"
MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def passwords() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        if "\t" in line and not line.startswith("#"):
            name, secret = line.split("\t", 1)
            result[name] = secret
    return result


def login(base: str, username: str, password: str) -> requests.Session:
    session = requests.Session()
    response = session.post(f"{base}/api/auth/login",
                            json={"username": username, "password": password}, timeout=30)
    response.raise_for_status()
    return session


def material_for(session: requests.Session, base: str, username: str) -> str:
    library = session.get(f"{base}/api/reading/library/materials", timeout=30).json()
    for item in library.get("materials") or []:
        if item.get("filename") == TEXTBOOK.name:
            return str(item["material_id"])
    # 学生账号按政策禁止上传；导入期间临时放开，导入后立刻由 write_policy 收回。
    write_policy(username, "", allow_upload=True)
    with TEXTBOOK.open("rb") as handle:
        response = session.post(f"{base}/api/reading/materials",
                                files={"file": (TEXTBOOK.name, handle, MIME)}, timeout=600)
    response.raise_for_status()
    return str(response.json()["material_id"])


def write_policy(username: str, material_id: str, *, allow_upload: bool = False) -> bool:
    record = get_user(username)
    if not record:
        return False
    user_id = str(record["id"])
    grant = load_grant(user_id) or empty_grant(user_id)
    wanted = {
        "age_band": "9-12",
        "locked_persona": "teacher",
        "allowed_capabilities": ["chat", "immersive_reading"],
        "default_capability": "chat",
        "allowed_surfaces": ["chat", "reading"],
        "reading": {
            "allow_upload": allow_upload,
            "material_ids": [material_id] if material_id else [],
            "extensions": [],
        },
    }
    if grant.get("learning_policy") == wanted:
        return False
    grant["learning_policy"] = wanted
    save_grant(user_id, grant)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    secrets_by_user = passwords()
    for index in range(1, 11):
        username = f"student{index:02d}"
        password = secrets_by_user.get(username)
        if not password:
            print(f"skip {username}: 无凭据")
            continue
        session = login(args.base, username, password)
        mid = material_for(session, args.base, username)
        changed = write_policy(username, mid)
        print(f"{username}: material={mid} policy_changed={changed}")


if __name__ == "__main__":
    main()
