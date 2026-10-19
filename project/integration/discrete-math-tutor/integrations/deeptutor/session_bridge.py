"""只在独立后端加载：以宿主身份创建上游课程和会话，不提升学生权限。"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class SessionBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str = Field(min_length=1, max_length=64)
    course_id: str = Field(min_length=1, max_length=64)
    course_title: str = Field(min_length=1, max_length=60)
    session_id: str = Field(min_length=1, max_length=64)


class SessionBridge:
    def __init__(self, home: Path):
        self.root = home.resolve() / "heart-bridge"
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = self.root / "bindings.sqlite3"
        self.lock = asyncio.Lock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    host_id TEXT PRIMARY KEY, upstream_id TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS courses (
                    user_id TEXT NOT NULL, host_id TEXT NOT NULL, upstream_id TEXT NOT NULL,
                    PRIMARY KEY(user_id, host_id));
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id TEXT NOT NULL, course_id TEXT NOT NULL, host_id TEXT NOT NULL,
                    upstream_id TEXT UNIQUE NOT NULL,
                    PRIMARY KEY(user_id, course_id, host_id));
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.registry, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    async def bind(self, request: SessionBindingRequest) -> dict:
        from deeptutor.multi_user.models import CurrentUser, UserScope
        from deeptutor.multi_user.paths import user_context
        from deeptutor.services.courses import CourseService
        from deeptutor.services.session import get_sqlite_session_store

        # 注册表和课程创建在同一进程串行；数据库唯一键同时约束重复映射。
        async with self.lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT upstream_id FROM users WHERE host_id=?", (request.student_id,)).fetchone()
                user_id = row[0] if row else "heart_" + hashlib.sha256(request.student_id.encode()).hexdigest()
                if row is None:
                    db.execute("INSERT INTO users VALUES (?, ?)", (request.student_id, user_id))
                scope = UserScope(kind="user", user_id=user_id, root=self.root / "users" / user_id)
                user = CurrentUser(id=user_id, username=user_id, role="student", scope=scope)
                with user_context(user):
                    courses = CourseService()
                    row = db.execute("SELECT upstream_id FROM courses WHERE user_id=? AND host_id=?",
                                     (user_id, request.course_id)).fetchone()
                    if row:
                        course = courses.get(row[0])
                    else:
                        # 崩溃可能发生在上游写入后、映射提交前；固定名称允许安全重认领。
                        suffix = hashlib.sha256(request.course_id.encode()).hexdigest()[:12]
                        name = request.course_title[:40] + " · " + suffix
                        course = next((c for c in courses.list_courses() if c.name == name), None)
                        if course is None:
                            course = courses.create(name=name, description="宿主课程：" + request.course_id,
                                instructions="教材引用与学习进度必须通过宿主课程的证据和作答校验。", default_capability="chat")
                        db.execute("INSERT INTO courses VALUES (?, ?, ?)", (user_id, request.course_id, course.id))
                    row = db.execute("SELECT upstream_id FROM sessions WHERE user_id=? AND course_id=? AND host_id=?",
                                     (user_id, request.course_id, request.session_id)).fetchone()
                    # 使用完整映射键生成 ID，断电重试也不会遗留第二个上游会话。
                    key = "\0".join((user_id, request.course_id, request.session_id))
                    session_id = row[0] if row else "heart_" + hashlib.sha256(key.encode()).hexdigest()
                    store = get_sqlite_session_store()
                    if await store.get_session(session_id) is None:
                        await store.create_session(title=request.course_title, session_id=session_id)
                    await store.update_session_preferences(session_id, {"course_id": course.id, "heart_managed": True})
                    from .published_course import COURSE, register_course_knowledge
                    if request.course_id == COURSE and (self.root.parent / "published" / COURSE / "current.json").is_file():
                        await asyncio.to_thread(register_course_knowledge, self.root.parent, courses, course.id)
                    if row is None:
                        db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (user_id, request.course_id, request.session_id, session_id))
                return {"user_id": user_id, "course_id": course.id, "session_id": session_id,
                        "role": "student", "model_execution_verified": False}


def require_bridge_token(x_heart_bridge_token: str = Header(default="")):
    expected = os.getenv("DEEPTUTOR_BRIDGE_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(503, "宿主接入凭据未配置")
    if not hmac.compare_digest(x_heart_bridge_token.encode(), expected.encode()):
        raise HTTPException(401, "宿主接入凭据无效")


def install_session_bridge(app, home: Path) -> SessionBridge:
    bridge = SessionBridge(home)
    router = APIRouter(prefix="/internal/heart")

    @router.post("/session", dependencies=[Depends(require_bridge_token)])
    async def bind_session(payload: SessionBindingRequest):
        return await bridge.bind(payload)

    app.include_router(router)
    return bridge
