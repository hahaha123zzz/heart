"""把固定教材写进学生账号的 learning_policy（只读、禁止上传）。

用法：python scripts/assign_fixed_reading.py [material_id]
material_id 缺省时从 .runtime/reading-upload.json 读取。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".." / ".." / "vendor" / "DeepTutor"))

from deeptutor.multi_user.grants import empty_grant, load_grant, save_grant  # noqa: E402
from deeptutor.multi_user.identity import get_user  # noqa: E402


def material_id() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    payload = json.loads((ROOT / ".runtime" / "reading-upload.json").read_text(encoding="utf-8-sig"))
    return str(payload["material_id"])


def policy(mid: str) -> dict:
    return {
        "age_band": "9-12",
        "locked_persona": "teacher",
        "allowed_capabilities": ["chat", "immersive_reading"],
        "default_capability": "chat",
        "allowed_surfaces": ["chat", "reading"],
        "reading": {"allow_upload": False, "material_ids": [mid], "extensions": []},
    }


def main() -> None:
    mid = material_id()
    updated = 0
    for index in range(1, 11):
        username = f"student{index:02d}"
        record = get_user(username)
        if not record:
            print(f"skip {username}")
            continue
        user_id = str(record["id"])
        grant = load_grant(user_id) or empty_grant(user_id)
        wanted = policy(mid)
        if grant.get("learning_policy") != wanted:
            grant["learning_policy"] = wanted
            save_grant(user_id, grant)
            updated += 1
    print(f"material_id={mid} updated={updated}")


if __name__ == "__main__":
    main()
