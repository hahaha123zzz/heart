"""H PostgreSQL 中的个人模型配置；密钥由部署环境独立提供。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.dialects.postgresql import insert

from database.database import engine, session_scope
from database.models import StudentModelCredential, AssessmentJobRow, AssessmentQueueSetting, StudentModelCheck


_runtime_snapshot = ContextVar("heart_model_snapshot", default=None)


@contextmanager
def use_snapshot(student_id: str, config: dict):
    token = _runtime_snapshot.set((student_id, dict(config)))
    try:
        yield
    finally:
        _runtime_snapshot.reset(token)


def runtime_config(student_id: str) -> dict | None:
    snapshot = _runtime_snapshot.get()
    if snapshot is not None:
        if snapshot[0] != student_id:
            raise RuntimeError("个人模型快照不属于当前学生")
        return dict(snapshot[1])
    return read(student_id, decrypt=True)


def _cipher() -> Fernet:
    key = os.environ.get("HEART_MODEL_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("未配置 HEART_MODEL_ENCRYPTION_KEY，个人模型暂不可用")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError):
        raise RuntimeError("HEART_MODEL_ENCRYPTION_KEY 格式无效") from None


def ensure_table() -> None:
    for model in (StudentModelCredential, AssessmentQueueSetting, AssessmentJobRow, StudentModelCheck):
        model.__table__.create(engine, checkfirst=True)
    from sqlalchemy import text
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE assessment_queue_settings ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 0"))


def read(student_id: str, *, decrypt: bool = False) -> dict | None:
    with session_scope() as session:
        row = session.get(StudentModelCredential, student_id)
        if row is None:
            return None
        result = {"credential_version": sha256(row.ciphertext.encode("ascii")).hexdigest(), "configured": True, "base_url": row.base_url, "model": row.model,
                  "api_key_masked": "••••" + row.tail,
                  "updated_at": row.updated_at.isoformat(timespec="microseconds")}
        if decrypt:
            try:
                result["api_key"] = _cipher().decrypt(row.ciphertext.encode("ascii")).decode("utf-8")
            except InvalidToken:
                raise RuntimeError("个人模型凭据无法解密，请重新保存 Key") from None
        return result


def save(student_id: str, base_url: str, model: str, api_key: str) -> str:
    ciphertext = _cipher().encrypt(api_key.encode("utf-8")).decode("ascii")
    values = dict(student_id=student_id, base_url=base_url, model=model,
                  ciphertext=ciphertext, tail=api_key[-4:], updated_at=datetime.now(timezone.utc).replace(tzinfo=None))
    with session_scope(immediate=True) as session:
        session.execute(insert(StudentModelCredential).values(**values).on_conflict_do_update(
            index_elements=[StudentModelCredential.student_id], set_=values))
        from integrations.deeptutor.assessment_jobs import credentials_changed
        credentials_changed(session, student_id, available=False, reason="assessment_unverified")
    return sha256(ciphertext.encode("ascii")).hexdigest()


def delete(student_id: str) -> None:
    with session_scope(immediate=True) as session:
        row = session.get(StudentModelCredential, student_id)
        if row is not None:
            session.delete(row)
        from integrations.deeptutor.assessment_jobs import credentials_changed
        credentials_changed(session, student_id, available=False)
