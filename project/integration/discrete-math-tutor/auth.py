"""正式学生账号：不暴露可自行指定的 student_id，学习数据由会话归属决定。"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
import uuid
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.database import session_scope
from database.models import AuthSessionRow, Student, UserRow

router = APIRouter(prefix="/api/auth", tags=["账号"])
PASSWORDS = PasswordHasher()
COOKIE_NAME = "dm_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
USERNAME = re.compile(r"^[A-Za-z0-9_]{3,32}$")


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


def _same_origin(request: Request) -> None:
    """拒绝浏览器跨站写入；本应用不开放跨域凭据请求。"""
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "跨站请求已拒绝")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if (parsed.scheme != request.url.scheme or
                parsed.netloc.lower() != request.headers.get("host", "").lower()):
            raise HTTPException(403, "请求来源不匹配")


def _secure_cookie(request: Request) -> bool:
    return request.url.scheme == "https" or os.getenv("AUTH_COOKIE_SECURE") == "1"


def _create_session(response: Response, request: Request,
                    user_id: int, username: str, student_id: str) -> dict:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    with session_scope() as session:
        session.add(AuthSessionRow(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                   user_id=user_id, csrf_token=csrf,
                                   expires_at=dt.datetime.utcnow() + dt.timedelta(seconds=SESSION_SECONDS)))
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=_secure_cookie(request), samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"username": username, "student_id": student_id, "csrf_token": csrf}


def current_identity(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "请先登录")
    with session_scope() as session:
        row = session.get(AuthSessionRow, hashlib.sha256(token.encode()).hexdigest())
        if not row or row.expires_at <= dt.datetime.utcnow():
            raise HTTPException(401, "登录已过期，请重新登录")
        user = session.get(UserRow, row.user_id)
        if not user:
            raise HTTPException(401, "账号不可用")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            _same_origin(request)
            received = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(received, row.csrf_token):
                raise HTTPException(403, "安全令牌无效，请刷新页面")
        return {"user_id": user.id, "username": user.username,
                "student_id": user.student_id, "csrf_token": row.csrf_token}


def current_student_id(identity: dict = Depends(current_identity)) -> str:
    return identity["student_id"]


def require_owner(requested: str, actual: str) -> str:
    if requested != actual:
        raise HTTPException(404, "学习记录不存在")
    return actual


@router.post("/register")
def register(credentials: Credentials, request: Request, response: Response):
    _same_origin(request)
    username = credentials.username.strip().lower()
    if not USERNAME.fullmatch(username):
        raise HTTPException(422, "用户名仅可使用 3–32 位字母、数字或下划线")
    password_hash = PASSWORDS.hash(credentials.password)
    student_id = "user-" + uuid.uuid4().hex
    try:
        with session_scope() as session:
            session.add(Student(student_id=student_id, account_type="production"))
            session.flush()
            user = UserRow(username=username, password_hash=password_hash, student_id=student_id)
            session.add(user)
            session.flush()
            user_id = user.id
    except IntegrityError:
        raise HTTPException(409, "用户名已被使用") from None
    return _create_session(response, request, user_id, username, student_id)


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response):
    _same_origin(request)
    with session_scope() as session:
        user = session.scalar(select(UserRow).where(UserRow.username == credentials.username.strip().lower()))
        if not user:
            raise HTTPException(401, "用户名或密码错误")
        try:
            PASSWORDS.verify(user.password_hash, credentials.password)
        except (VerifyMismatchError, VerificationError):
            raise HTTPException(401, "用户名或密码错误") from None
        user_id, username, student_id = user.id, user.username, user.student_id
    return _create_session(response, request, user_id, username, student_id)


@router.get("/me")
def me(identity: dict = Depends(current_identity)):
    return identity


@router.post("/logout")
def logout(request: Request, response: Response, identity: dict = Depends(current_identity)):
    token = request.cookies.get(COOKIE_NAME, "")
    with session_scope() as session:
        row = session.get(AuthSessionRow, hashlib.sha256(token.encode()).hexdigest())
        if row:
            session.delete(row)
    response.delete_cookie(COOKIE_NAME, path="/", secure=_secure_cookie(request), samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
