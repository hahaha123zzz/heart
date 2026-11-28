"""将正式实验心理学全套教材授权给已初始化的十个评审账号。"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.provision_review_accounts import HOST, VENDOR, NAMES, read_credentials


def assign(home: Path, assets: Path):
    from deeptutor.multi_user import identity
    from deeptutor.multi_user.grants import load_grant, save_grant, learner_grant
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user, user_context
    from deeptutor.services import auth
    from integrations.deeptutor.course_reading import _course_documents, import_course_reading

    if not identity.USERS_FILE.resolve().is_relative_to(home) or not auth.AUTH_ENABLED or auth.POCKETBASE_ENABLED:
        raise ValueError("目标不是指定目录的本地厂家认证实例")
    secret_file = home / ".runtime/review-accounts/vendor-accounts.txt"
    if secret_file.resolve() != secret_file:
        raise ValueError("凭据文件不能指向别处")
    credentials = read_credentials(secret_file)
    users = {}
    for name in NAMES:
        record = identity.get_user(name)
        if (not record or name not in credentials or record.get("role") != "user" or record.get("preset") != "learner"
                or record.get("disabled") or not auth.verify_password(credentials[name], record["hash"])):
            raise ValueError(f"评审账号 {name} 缺失或与初始化身份不符")
        users[name] = record["id"]
    prepared = _course_documents(assets)
    results = {}
    for name, user_id in users.items():
        scope = scope_for_user(user_id, is_admin=False)
        with user_context(CurrentUser(id=user_id, username=name, role="user", scope=scope)):
            reading = import_course_reading(prepared)
            ids = [item["material_id"] for item in reading["materials"]]
            policy = learner_grant(user_id)["learning_policy"]
            policy["default_capability"] = "chat"
            policy["allowed_capabilities"] = ["chat", "immersive_reading", "mastery_path", "visualize"]
            policy["reading"]["material_ids"] = ids
            policy["reading"]["extensions"] = ["read_aloud"]
            grant = load_grant(user_id)
            if grant.get("learning_policy") != policy:
                grant["learning_policy"] = policy
                save_grant(user_id, grant)
            results[name] = reading
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True, help="已完成评审账号初始化、且 worker 已停止的目录")
    parser.add_argument("--course-assets", type=Path, default=HOST / "knowledge/courses/experimental-psychology-3")
    args = parser.parse_args()
    home = args.home.resolve(strict=True)
    os.environ["DEEPTUTOR_HOME"] = str(home)
    sys.path[:0] = [str(HOST), str(VENDOR)]
    results = assign(home, args.course_assets.resolve(strict=True))
    print(f"已核验并授权 {len(results)} 个评审账号，每个账号 {len(next(iter(results.values()))['materials'])} 章。")


if __name__ == "__main__":
    main()
