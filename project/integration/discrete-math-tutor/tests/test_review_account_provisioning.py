"""永久评审账号在隔离厂家目录和随机 PG 库验收。"""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys


def test_review_accounts_are_empty_permanent_and_idempotent(tmp_path, monkeypatch):
    import asyncio
    import json
    from tests.pg_support import temp_databases
    from sqlalchemy.engine import make_url
    from scripts.provision_review_accounts import NAMES, provision, occupied_host_names
    from pytest import raises

    home = tmp_path / "vendor-home"
    for key in ("AUTH_USERNAME", "AUTH_PASSWORD_HASH", "POCKETBASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DEEPTUTOR_HOME", str(home))
    settings = home / "data/user/settings"
    settings.mkdir(parents=True)
    (settings / "auth.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
    with temp_databases("heart_review_accounts") as env:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        from database.database import engine, session_scope
        from database.models import AuthAccountRow, Base, Student
        assert engine.url.database in {make_url(env[k]).database for k in ("DATABASE_URL", "COURSE_DATABASE_URL")}
        Base.metadata.create_all(engine)
        try:
            from deeptutor.services import auth
            from deeptutor.multi_user import identity
            assert identity.USERS_FILE.resolve().is_relative_to(home)
            auth.add_user("test-admin", "local-test-admin-" * 2, role="admin")
            auth.add_user(NAMES[0], "unrelated-existing-user", role="user", preset="learner")
            with raises(ValueError, match="已占用"):
                provision(home)
            assert not (home / ".runtime/review-accounts/vendor-accounts.txt").exists()
            assert auth.delete_user(NAMES[0])
            with session_scope() as session:
                session.add(Student(student_id=NAMES[0], account_type="test"))
            with raises(ValueError, match="H 中已有同名数据"):
                provision(home)
            assert auth.get_user_info(NAMES[0]) is None
            with session_scope() as session:
                session.delete(session.get(Student, NAMES[0]))
            with session_scope() as session:
                session.add(AuthAccountRow(student_id="old-alias", username=NAMES[0], password_hash="fixture"))
            with raises(ValueError, match="H 中已有同名数据"):
                provision(home)
            with session_scope() as session:
                session.delete(session.get(AuthAccountRow, "old-alias"))
            assert not occupied_host_names(NAMES)
            created, path = provision(home)
            assert created == 10 and path.is_relative_to(home / ".runtime")
            raw = path.read_bytes()
            creds = dict(line.split("\t", 1) for line in raw.decode().splitlines())
            assert set(creds) == set(NAMES) and len(set(creds.values())) == 10
            assert all(len(password) >= 40 for password in creds.values())
            users = {name: auth.authenticate(name, password) for name, password in creds.items()}
            assert all(user and user.role == "user" for user in users.values())
            assert len({u.user_id for u in users.values()}) == 10
            wrong_login = auth.authenticate(NAMES[0], creds[NAMES[1]])
            assert wrong_login is None
            assert not occupied_host_names(NAMES), "初始化不写学习库"

            from database.repository import Repository
            from database.account_manager import AccountManager
            repo = Repository()
            for name in NAMES:
                repo.ensure_student(name)
            with session_scope() as session:
                for name in NAMES:
                    row = session.get(Student, name)
                    assert row.expires_at is None and row.account_type != "test"
                session.add(Student(student_id="expired-test", account_type="test", expires_at=datetime(2000, 1, 1)))
            assert AccountManager(repo).cleanup_expired() == 1
            assert repo.clear_test_accounts_on_code_change("test-review") == 0

            from deeptutor.multi_user.models import CurrentUser
            from deeptutor.multi_user.paths import user_context, scope_for_user
            from deeptutor.services.session import get_sqlite_session_store
            def scope(name):
                uid = users[name].user_id
                return user_context(CurrentUser(id=uid, username=name, role="user", scope=scope_for_user(uid, is_admin=False)))
            with scope(NAMES[0]):
                first = get_sqlite_session_store()
                asyncio.run(first.create_session(title="保留的会话", session_id="kept-session"))
            with scope(NAMES[1]):
                assert asyncio.run(get_sqlite_session_store().get_session("kept-session")) is None
            script = Path(__file__).resolve().parents[1] / "scripts/provision_review_accounts.py"
            child_env = {**os.environ, "PYTHONPATH": os.pathsep.join(path for path in sys.path if path)}
            run = subprocess.run([sys.executable, str(script), "--home", str(home)], env=child_env, capture_output=True, timeout=90)
            assert run.returncode == 0, "离线脚本在新进程中重跑失败"
            unchanged = path.read_bytes() == raw
            assert unchanged
            assert {name: auth.get_user_info(name)["id"] for name in NAMES} == {name: user.user_id for name, user in users.items()}
            with scope(NAMES[0]):
                assert asyncio.run(get_sqlite_session_store().get_session("kept-session"))["title"] == "保留的会话"

            from scripts.assign_review_reading import assign
            from deeptutor.multi_user.grants import load_grant
            from deeptutor.reading import ReadingCatalogStore, ReadingStore
            from hashlib import sha256
            assets = os.getenv("HEART_TEST_REVIEW_COURSE_ASSETS")
            if assets:
                asset_root = Path(assets)
            else:
                import pymupdf
                asset_root = tmp_path / "test-course-assets"
                rows = []
                for chapter in range(1, 12):
                    path_pdf = asset_root / "chapters" / f"chapter_{chapter:02d}" / f"chapter_{chapter:02d}.generated.pdf"
                    path_pdf.parent.mkdir(parents=True)
                    with pymupdf.open() as doc:
                        doc.new_page().insert_text((40, 60), f"Test chapter {chapter}")
                        doc.save(path_pdf)
                    rows.append({"document_id": f"test-chapter-{chapter}", "chapter_id": chapter,
                        "course_id": "experimental-psychology-3", "version": sha256(path_pdf.read_bytes()).hexdigest()})
                (asset_root / "pdf_manifest.json").write_text(json.dumps(rows), encoding="utf-8")
            prepared = assign(home, asset_root)
            assert len(prepared) == 10 and len({x["workspace_id"] for x in prepared.values()}) == 10
            first_reading = prepared[NAMES[0]]
            ids = {item["material_id"] for item in first_reading["materials"]}
            assert len(ids) == 11
            for name, reading in prepared.items():
                policy = load_grant(users[name].user_id)["learning_policy"]
                assert set(policy["reading"]["material_ids"]) == ids and not policy["reading"]["allow_upload"]
                assert policy["reading"]["extensions"] == ["read_aloud"]
                assert len(reading["materials"]) == 11
            with scope(NAMES[0]):
                unrelated = tmp_path / "other-material.txt"
                unrelated.write_text("Unassigned material", encoding="utf-8")
                other_manifest = ReadingStore().ingest(unrelated)
                ReadingCatalogStore().register_manifest(other_manifest)
            assert assign(home, asset_root) == prepared

            from fastapi import FastAPI, Depends
            from fastapi.testclient import TestClient
            from deeptutor.api.routers import auth as router, reading as reading_router
            from jose import jwt
            app = FastAPI()
            app.include_router(router.router, prefix="/api/auth")
            app.include_router(reading_router.router, prefix="/api/reading", dependencies=[Depends(router.require_learning_surface)])
            with TestClient(app) as client:
                assert client.post("/api/auth/login", json={"username": NAMES[0], "password": creds[NAMES[0]]}).status_code == 200
                assert client.get("/api/auth/status").json()["authenticated"]
                base = "/api/reading"
                listing = client.get(base + "/materials")
                assert listing.status_code == 200 and {item["material_id"] for item in listing.json()} == ids
                mid = first_reading["active_material_id"]
                assert client.get(base + f"/materials/{mid}/raw").content.startswith(b"%PDF")
                assert client.get(base + f"/materials/{other_manifest.material_id}").status_code == 403
                assert client.delete(base + f"/materials/{mid}").status_code == 403
                assert client.post(base + "/materials", files={"file": ("test.txt", b"unapproved")}).status_code == 403
                workspace = first_reading["workspace_id"]
                assert client.get(base + f"/workspaces/{workspace}").status_code == 200
                assert client.post(base + f"/workspaces/{workspace}/sessions", json={"title": "第一人阅读", "active_material_id": mid}).status_code == 201
                with TestClient(app) as second:
                    second_login = second.post("/api/auth/login", json={"username": NAMES[1], "password": creds[NAMES[1]]})
                    assert second_login.status_code == 200
                    assert second.get(base + f"/workspaces/{workspace}").status_code == 404
                    own_workspace = prepared[NAMES[1]]["workspace_id"]
                    assert second.get(base + f"/workspaces/{own_workspace}").json()["sessions"] == []
                assert client.get("/api/auth/users").status_code == 403
                assert client.delete(f"/api/auth/users/{NAMES[1]}").status_code == 403
                assert client.post("/api/auth/logout").status_code == 200
                assert not client.get("/api/auth/status").json()["authenticated"]
                token = auth.create_token(NAMES[0], "user", users[NAMES[0]].user_id)
                expired = jwt.get_unverified_claims(token)
                expired["exp"] = datetime.now(timezone.utc) - timedelta(minutes=5)
                assert auth.decode_token(jwt.encode(expired, auth.AUTH_SECRET, algorithm=auth._ALGORITHM)) is None
        finally:
            (home / ".runtime/review-accounts/vendor-accounts.txt").unlink(missing_ok=True)
            engine.dispose()
