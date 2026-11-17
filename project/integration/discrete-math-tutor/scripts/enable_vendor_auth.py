"""打开厂家认证（V/web 与厂家 worker 共用同一套登录）。

幂等：只写 `auth.json` 的 enabled/cookie_secure/token_expire_hours，不动用户表。
账号另由 scripts/init_vendor_accounts.py 创建。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".." / ".." / "vendor" / "DeepTutor"))

from deeptutor.services.config.runtime_settings import (  # noqa: E402
    get_runtime_settings_service,
)


def main() -> None:
    service = get_runtime_settings_service()
    saved = service.save_auth(
        {"enabled": True, "cookie_secure": False, "token_expire_hours": 24})
    print(f"settings_dir={service.settings_dir} enabled={saved['enabled']}")


if __name__ == "__main__":
    main()
