"""登录会话契约：/api/auth/status|login|logout，供 V/web 的 lib/auth.ts 直接消费。"""
import importlib
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.pg_support import temp_databases


def _prepare():
    import database.database as db
    importlib.reload(db)
    db.init_db()
    import auth_api
    importlib.reload(auth_api)
    return auth_api


def _client(auth_api):
    app = FastAPI()
    app.include_router(auth_api.router)
    return TestClient(app)


def test_status_login_logout_flow():
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["TUTOR_COURSE"] = "experimental-psychology-3"
        auth_api = _prepare()
        auth_api.create_account("s01", "pw-strong-1")
        client = _client(auth_api)

        initial = client.get("/api/auth/status").json()
        assert initial["enabled"] is True
        assert initial["authenticated"] is False
        assert initial["user_id"] is None

        assert client.post("/api/auth/login",
            json={"username": "s01", "password": "wrong"}).status_code == 401

        ok = client.post("/api/auth/login",
            json={"username": "s01", "password": "pw-strong-1"})
        assert ok.status_code == 200
        assert "heart_session" in client.cookies

        status = client.get("/api/auth/status").json()
        assert status["authenticated"] is True
        assert status["user_id"] == "s01"
        assert status["role"] == "student"

        client.post("/api/auth/logout")
        assert client.get("/api/auth/status").json()["authenticated"] is False


def test_expired_session_is_rejected():
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["TUTOR_COURSE"] = "experimental-psychology-3"
        auth_api = _prepare()
        auth_api.create_account("s02", "pw-strong-2")
        client = _client(auth_api)
        client.post("/api/auth/login", json={"username": "s02", "password": "pw-strong-2"})
        token = client.cookies["heart_session"]
        auth_api.expire_session(token)
        assert client.get("/api/auth/status").json()["authenticated"] is False


def test_account_creation_is_idempotent():
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["TUTOR_COURSE"] = "experimental-psychology-3"
        auth_api = _prepare()
        first = auth_api.create_account("s03", "pw-strong-3")
        second = auth_api.create_account("s03", "different")
        assert first is True
        assert second is False
        client = _client(auth_api)
        assert client.post("/api/auth/login",
            json={"username": "s03", "password": "pw-strong-3"}).status_code == 200
        assert client.post("/api/auth/login",
            json={"username": "s03", "password": "different"}).status_code == 401
