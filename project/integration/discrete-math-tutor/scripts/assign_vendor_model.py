"""把宿主模型授予学生账号（过渡方案，学生自带 Key 接入前的共享模型）。

幂等：只替换该 profile 的授权条目，不动其他模型与工具授权。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".." / ".." / "vendor" / "DeepTutor"))

from deeptutor.multi_user.grants import empty_grant, load_grant, save_grant  # noqa: E402
from deeptutor.multi_user.identity import get_user  # noqa: E402
from deeptutor.services.config.runtime_settings import (  # noqa: E402
    get_runtime_settings_service,
)


def host_profile_id() -> str:
    settings = get_runtime_settings_service()
    import json

    data = json.loads((settings.settings_dir / "model_catalog.json").read_text(encoding="utf-8"))
    profiles = ((data.get("services") or {}).get("llm") or {}).get("profiles") or []
    if not profiles:
        raise SystemExit("模型目录为空，请先由宿主跑一轮以生成 heart-host profile")
    return str(profiles[0]["id"])


def main() -> None:
    profile_id = host_profile_id()
    granted = 0
    for index in range(1, 11):
        username = f"student{index:02d}"
        record = get_user(username)
        if not record:
            print(f"skip {username}: 账号不存在")
            continue
        user_id = str(record["id"])
        grant = load_grant(user_id) or empty_grant(user_id)
        models = grant.setdefault("models", {}).setdefault("llm", [])
        entry = {"profile_id": profile_id, "model_ids": ["host-model"]}
        if entry not in models:
            models[:] = [m for m in models if m.get("profile_id") != profile_id] + [entry]
            save_grant(user_id, grant)
            granted += 1
    print(f"profile={profile_id} granted={granted}")


if __name__ == "__main__":
    main()
