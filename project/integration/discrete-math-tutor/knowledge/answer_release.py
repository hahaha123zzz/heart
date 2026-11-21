"""Versioned rollout and fail-closed state for answer-quality features."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "knowledge/releases/query-accuracy-v1.json"
CIRCUIT_STATE = ROOT / ".runtime/answer-release/circuit-open.json"
MODES = frozenset({"off", "shadow", "canary", "active"})


@dataclass(frozen=True)
class ReleaseDecision:
    mode: str
    active: bool
    shadow: bool
    feature: str
    release_id: str
    bucket: int | None
    reason: str


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity_payload(manifest: dict) -> dict:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"release_id", "created_at"}
    }


def expected_release_id(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            _identity_payload(manifest),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def verify(manifest_path: Path | None = None) -> dict:
    path = MANIFEST if manifest_path is None else manifest_path
    manifest = _load(path)
    gaps: list[str] = []
    if manifest.get("schema") != "answer-accuracy-release-v1":
        gaps.append("发布清单格式无效")
    if manifest.get("release_id") != expected_release_id(manifest):
        gaps.append("发布标识与清单内容不一致")
    for item in manifest.get("artifacts", []):
        target = ROOT / item["path"]
        try:
            actual = sha256_path(target)
        except OSError:
            gaps.append(f"文件缺失：{item['path']}")
            continue
        if actual != item.get("sha256"):
            gaps.append(f"文件哈希变化：{item['path']}")
    return {
        "ok": not gaps,
        "gaps": gaps,
        "manifest": manifest,
        "release_id": manifest.get("release_id", ""),
    }


@lru_cache(maxsize=8)
def _verified_state(path_value: str, modified_ns: int) -> tuple[bool, str, str]:
    del modified_ns
    state = verify(Path(path_value))
    return (
        bool(state["ok"]),
        str(state["release_id"]),
        "；".join(state["gaps"]),
    )


def _bucket(release_id: str, feature: str, student_id: str) -> int:
    key = f"{release_id}\0{feature}\0{student_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % 1000


def _open_circuits(path: Path) -> set[str]:
    state = _load(path)
    if state.get("global"):
        return {"*"}
    return set(state.get("features") or ())


def decision(
    feature: str,
    *,
    student_id: str,
    account_type: str = "production",
    manifest_path: Path | None = None,
    circuit_path: Path | None = None,
) -> ReleaseDecision:
    path = MANIFEST if manifest_path is None else manifest_path
    try:
        verified, release_id, gaps = _verified_state(
            str(path.resolve()), path.stat().st_mtime_ns
        )
    except OSError:
        verified, release_id, gaps = False, "", "发布清单不可读"
    manifest = _load(path)
    policy = (manifest.get("features") or {}).get(feature) or {}
    if not verified:
        return ReleaseDecision(
            mode="off",
            active=False,
            shadow=False,
            feature=feature,
            release_id=release_id,
            bucket=None,
            reason=gaps or "发布哈希校验失败",
        )
    open_circuits = _open_circuits(
        CIRCUIT_STATE if circuit_path is None else circuit_path
    )
    if "*" in open_circuits or feature in open_circuits:
        return ReleaseDecision(
            mode="off",
            active=False,
            shadow=False,
            feature=feature,
            release_id=release_id,
            bucket=None,
            reason="功能已由自动熔断关闭",
        )
    env_name = "ANSWER_RELEASE_" + feature.upper() + "_MODE"
    mode = os.getenv(env_name, str(policy.get("mode") or "off")).strip().lower()
    if mode not in MODES:
        mode = "off"
    percent = float(
        os.getenv(
            "ANSWER_RELEASE_" + feature.upper() + "_PERCENT",
            str(policy.get("percent", 0)),
        )
    )
    if not 0 <= percent <= 100:
        return ReleaseDecision(
            mode="off",
            active=False,
            shadow=False,
            feature=feature,
            release_id=release_id,
            bucket=None,
            reason="灰度比例无效",
        )
    if mode == "active" or (
        account_type == "test" and policy.get("test_accounts_active", False)
    ):
        return ReleaseDecision(
            mode="active",
            active=True,
            shadow=False,
            feature=feature,
            release_id=release_id,
            bucket=None,
            reason="测试账号启用" if mode != "active" else "策略全量启用",
        )
    bucket = _bucket(release_id, feature, student_id or "anonymous")
    active = mode == "canary" and bucket < round(percent * 10)
    shadow = mode in {"shadow", "canary"} and not active
    return ReleaseDecision(
        mode="canary" if mode == "canary" else mode,
        active=active,
        shadow=shadow,
        feature=feature,
        release_id=release_id,
        bucket=bucket,
        reason=(
            "命中灰度桶" if active
            else "未命中灰度桶，保持旧路径" if mode == "canary"
            else "shadow 不影响回答" if mode == "shadow"
            else "功能关闭"
        ),
    )
