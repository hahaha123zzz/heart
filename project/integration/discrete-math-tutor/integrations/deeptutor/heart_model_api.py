"""学生自带模型 Key：加密保存、脱敏读取、删除，并注入厂家模型授权。

存储放在厂家 home 的 `data/system/heart-model/`（Fernet 密文）；明文 Key 只在该
学生自己的 model_catalog profile 里出现一次，和厂家自身的设计一致。
"""
from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deeptutor.api.routers.auth import require_auth, TokenPayload
from deeptutor.multi_user.grants import empty_grant, load_grant, save_grant
from deeptutor.multi_user.model_access import admin_catalog_service


class ModelKeyRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=2048)
    model: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=1, max_length=512)


def _check_endpoint(base_url: str) -> str:
    """只允许 HTTPS 公网端点，挡住 localhost / 内网 / 云元数据地址。"""
    parts = urlsplit(base_url)
    if parts.scheme != "https" or not parts.hostname:
        raise HTTPException(400, "Base URL 必须是 https 公网地址")
    if parts.username or parts.password:
        raise HTTPException(400, "Base URL 不能包含凭据")
    host = parts.hostname.lower()
    if host in {"localhost", "metadata.google.internal"}:
        raise HTTPException(400, "Base URL 不能指向本机或云元数据地址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return base_url
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise HTTPException(400, "Base URL 不能指向内网地址")
    return base_url


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def install_heart_model(app, home: Path) -> None:
    root = Path(home) / "data" / "system" / "heart-model"
    root.mkdir(parents=True, exist_ok=True)
    secret_file = root / ".secret"
    if not secret_file.is_file():
        secret_file.write_bytes(Fernet.generate_key())
    fernet = Fernet(secret_file.read_bytes())

    def record_path(user_id: str) -> Path:
        return root / f"{user_id}.json"

    def load_record(user_id: str) -> dict | None:
        path = record_path(user_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def profile_id(user_id: str) -> str:
        return f"heart-student-{user_id[:12]}"

    def apply_profile(user_id: str, base_url: str, model: str, api_key: str) -> None:
        pid = profile_id(user_id)
        profile = {
            "id": pid, "name": "我的模型", "binding": "", "base_url": base_url,
            "api_key": api_key, "wire_api": "chat_completions",
            "models": [{"id": "student-model", "name": model, "model": model}],
        }
        catalog = admin_catalog_service()
        def update(value: dict) -> None:
            profiles = value["services"]["llm"]["profiles"]
            profiles[:] = [item for item in profiles if item["id"] != pid] + [profile]
        catalog.update(update)
        grant = load_grant(user_id) or empty_grant(user_id)
        grant["models"] = {"llm": [{"profile_id": pid, "model_ids": ["student-model"]}]}
        save_grant(user_id, grant)

    def clear_profile(user_id: str) -> None:
        pid = profile_id(user_id)
        catalog = admin_catalog_service()
        def update(value: dict) -> None:
            profiles = value["services"]["llm"]["profiles"]
            profiles[:] = [item for item in profiles if item["id"] != pid]
        catalog.update(update)
        grant = load_grant(user_id) or empty_grant(user_id)
        models = (grant.get("models") or {}).get("llm") or []
        grant["models"] = {"llm": [m for m in models if m.get("profile_id") != pid]}
        save_grant(user_id, grant)
        record_path(user_id).unlink(missing_ok=True)

    router = APIRouter(prefix="/api/heart", dependencies=[Depends(require_auth)])

    @router.get("/model")
    def read_model(payload: TokenPayload = Depends(require_auth)) -> dict:
        record = load_record(payload.user_id)
        if record is None:
            return {"configured": False}
        return {
            "configured": True,
            "base_url": record["base_url"],
            "model": record["model"],
            "api_key_masked": f"••••{record.get('tail', '')}",
            "updated_at": record.get("updated_at", ""),
        }

    @router.put("/model")
    def save_model(body: ModelKeyRequest, payload: TokenPayload = Depends(require_auth)) -> dict:
        base_url = _check_endpoint(body.base_url.strip().rstrip("/"))
        model = body.model.strip()
        api_key = body.api_key.strip()
        ciphertext = fernet.encrypt(api_key.encode("utf-8")).decode("ascii")
        record_path(payload.user_id).write_text(json.dumps({
            "base_url": base_url, "model": model, "ciphertext": ciphertext,
            "tail": api_key[-4:], "updated_at": _now(),
        }, ensure_ascii=False), encoding="utf-8")
        apply_profile(payload.user_id, base_url, model, api_key)
        return {"configured": True, "api_key_masked": f"••••{api_key[-4:]}"}

    @router.delete("/model")
    def delete_model(payload: TokenPayload = Depends(require_auth)) -> dict:
        clear_profile(payload.user_id)
        return {"configured": False}

    app.include_router(router)
