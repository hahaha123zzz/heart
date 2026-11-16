"""账号登录与会话（/api/auth/*）。

契约对齐 V/web `lib/auth.ts`：前端只读 `GET /api/auth/status` 的 `AuthStatus`，
并调用 `POST /api/auth/login` / `logout`。会话用 HttpOnly cookie，
身份即宿主 `student_id`，供后续接口按会话解析。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from database.database import session_scope
from database.models import AuthAccountRow, AuthSessionRow, Student

router = APIRouter(prefix="/api/auth")
COOKIE_NAME = "heart_session"
SESSION_HOURS = 12
ITERATIONS = 240_000
# shortcut: 会话固定 12 小时且不做续期，演示够用；需要长期在会话时改成滑动续期。
# shortcut: 未提供 learning_policy，前端因此不做功能裁剪；待教材 material_ids 接好后再下发。


def _utcnow() -> datetime:
    return datetime.utcnow()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)).hex()
    except (ValueError, TypeError):
        return False
    return algorithm == "pbkdf2_sha256" and hmac.compare_digest(expected, digest)


def create_account(student_id: str, password: str, *, role: str = "student") -> bool:
    """幂等建号：账号已存在返回 False，不重置密码。"""
    with session_scope() as session:
        if session.get(AuthAccountRow, student_id) is not None:
            return False
        session.add(AuthAccountRow(
            student_id=student_id, username=student_id,
            password_hash=hash_password(password), role=role))
        if session.get(Student, student_id) is None:
            session.add(Student(student_id=student_id, account_type="production", expires_at=None))
    return True


def _issue_session(student_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with session_scope() as session:
        session.add(AuthSessionRow(
            token_hash=_token_hash(token), student_id=student_id,
            expires_at=_utcnow() + timedelta(hours=SESSION_HOURS)))
    return token


def current_account(request: Request) -> AuthAccountRow | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    with session_scope() as session:
        row = session.get(AuthSessionRow, _token_hash(token))
        if row is None or row.revoked_at is not None or row.expires_at <= _utcnow():
            return None
        account = session.get(AuthAccountRow, row.student_id)
        if account is None:
            return None
        session.expunge(account)
        return account


def expire_session(token: str) -> None:
    with session_scope() as session:
        row = session.get(AuthSessionRow, _token_hash(token))
        if row is not None:
            row.revoked_at = _utcnow()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.get("/status")
def status(request: Request):
    account = current_account(request)
    return {
        "enabled": True,
        "authenticated": account is not None,
        "user_id": account.student_id if account else None,
        "username": account.username if account else None,
        "role": account.role if account else None,
        "is_admin": bool(account and account.role == "admin"),
        "preset": None,
        "avatar": "",
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    with session_scope() as session:
        account = session.scalar(
            select(AuthAccountRow).where(AuthAccountRow.username == payload.username))
        stored = account.password_hash if account else ""
    if not account or not verify_password(payload.password, stored):
        raise HTTPException(401, "账号或密码不正确")
    token = _issue_session(account.student_id)
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_HOURS * 3600,
        httponly=True, samesite="lax", path="/")
    return {"ok": True, "user_id": account.student_id, "role": account.role}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        expire_session(token)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/is_first_user")
def is_first_user():
    with session_scope() as session:
        return {"is_first_user": session.scalar(select(AuthAccountRow).limit(1)) is None}
