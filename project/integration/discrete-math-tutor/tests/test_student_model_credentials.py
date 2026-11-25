"""个人模型的 PostgreSQL 存储与厂家请求内隔离检查，不调用外部模型。"""
import os
import socket
from copy import deepcopy
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet


def _save_verified(store, owner, base_url, model, key):
    """旧生命周期用例使用固定能力结果；新验证门禁另有真实状态负例。"""
    from uuid import uuid4
    store.save(owner, base_url, model, key)
    from integrations.deeptutor import model_capabilities as checks
    vendor = "vendor-" + owner.removeprefix("queue-")
    vendor = {"queue-rate-limit": "vendor-rate", "queue-delete-race": "vendor-race"}.get(owner, vendor)
    version = store.read(owner)["credential_version"]
    dispatch, _ = checks.begin_check(owner, vendor, str(uuid4()), "assessment", version, confirm_cost=True)
    assert checks.finish_check(dispatch, "passed")


@pytest.fixture(scope="module")
def store():
    from tests.pg_support import temp_databases
    previous = dict(os.environ)
    try:
        with temp_databases("heart_model") as env:
            os.environ.update(env)
            os.environ["HEART_MODEL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
            from integrations.deeptutor import model_credentials
            from sqlalchemy.engine import make_url
            expected = {make_url(env[name]).database for name in ("DATABASE_URL", "COURSE_DATABASE_URL")}
            assert model_credentials.engine.url.database in expected, "测试连接必须指向本次随机临时库，禁止使用提前初始化的连接"
            try:
                model_credentials.ensure_table()
                yield model_credentials
            finally:
                model_credentials.engine.dispose()
    finally:
        os.environ.clear()
        os.environ.update(previous)


def test_encrypted_upsert_delete_and_owner_isolation(store):
    from database.models import StudentModelCredential
    _save_verified(store, "student-a", "https://public.example/v1", "model-a", "secret-a")
    _save_verified(store, "student-b", "https://public.example/v1", "model-b", "secret-b")
    assert store.read("student-a")["model"] == "model-a"
    assert "api_key" not in store.read("student-a")
    with store.session_scope() as session:
        row = session.get(StudentModelCredential, "student-a")
        assert "secret-a" not in row.ciphertext
    assert store.read("student-a", decrypt=True)["api_key"] == "secret-a"
    _save_verified(store, "student-a", "https://public.example/v1", "new-a", "replacement-a")
    assert store.read("student-a", decrypt=True)["api_key"] == "replacement-a"
    store.delete("student-a")
    store.delete("student-a")
    assert store.read("student-a") is None
    assert store.read("student-b", decrypt=True)["api_key"] == "secret-b"


def test_missing_and_wrong_encryption_key_fail_closed(store, monkeypatch):
    _save_verified(store, "key-test", "https://public.example/v1", "model", "private-key")
    monkeypatch.delenv("HEART_MODEL_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError, match="未配置"):
        _save_verified(store, "missing", "https://public.example", "model", "private-key")
    assert store.read("missing") is None
    monkeypatch.setenv("HEART_MODEL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match="无法解密"):
        store.read("key-test", decrypt=True)


def test_native_bridge_account_without_personal_key_can_use_host_grant(store, monkeypatch):
    from integrations.deeptutor.heart_model_api import _personal_profiles
    from deeptutor.multi_user.context import reset_current_user, set_current_user

    token = set_current_user(
        SimpleNamespace(id="native-user", username="heart_native_test", is_admin=False)
    )
    try:
        assert _personal_profiles(SimpleNamespace(
            id="native-user", username="heart_native_test", is_admin=False
        )) is None
        assert _personal_profiles(SimpleNamespace(
            id="student", username="ordinary-student", is_admin=False
        )) == []
    finally:
        reset_current_user(token)


@pytest.fixture
def personal_runtime(store, monkeypatch):
    from deeptutor.multi_user import personal_models
    from integrations.deeptutor.heart_model_api import _personal_profiles
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    monkeypatch.setattr(personal_models, "_external_llm_profiles", _personal_profiles)
    token = set_current_user(SimpleNamespace(id="vendor-a", username="runtime-a", is_admin=False))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kw: [(2, 1, 6, "", ("8.8.8.8", 443))])
    try:
        yield personal_models
    finally:
        reset_current_user(token)


def test_personal_runtime_replaces_shared_catalog_without_writing(store, personal_runtime, tmp_path):
    from deeptutor.multi_user.model_access import redacted_model_access
    _save_verified(store, "runtime-a", "https://public.example/v1", "private-model", "private-a-key")
    catalog = {"services": {"llm": {"profiles": [{"id": "shared", "api_key": "shared-key"}]},
                            "task": {"mode": "reference", "selection": {"profile_id": "shared"}}}}
    before = deepcopy(catalog)
    merged = personal_runtime.merge_personal_llm_profiles(catalog)
    assert catalog == before
    assert merged["services"]["llm"]["profiles"][0]["api_key"] == "private-a-key"
    assert len(merged["services"]["llm"]["profiles"]) == 1
    assert merged["services"]["task"] == {"mode": "inherit"}
    rows = redacted_model_access()["llm"]
    assert rows[0]["profile_id"] == "heart-student-vendor-a"
    assert "api_key" not in rows[0]
    assert redacted_model_access("vendor-b") == {"llm": []}
    from deeptutor.services.config.model_catalog import ModelCatalogService
    from deeptutor.services.config.provider_runtime import resolve_llm_runtime_config
    service = ModelCatalogService(tmp_path / "unused-catalog.json")
    for name in ("llm", "task"):
        resolved = resolve_llm_runtime_config(catalog, service=service, service_name=name)
        assert resolved.api_key == "private-a-key"
        assert resolved.base_url == "https://public.example/v1"
    assert not service.path.exists()


def test_deleted_key_and_loader_errors_never_restore_shared_key(store, personal_runtime, monkeypatch):
    from deeptutor.services.config.provider_runtime import _with_personal_llm_profiles
    store.delete("runtime-a")
    with pytest.raises(PermissionError):
        _with_personal_llm_profiles({"services": {}})
    def broken(user):
        raise RuntimeError("storage unavailable")
    monkeypatch.setattr(personal_runtime, "_external_llm_profiles", broken)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        _with_personal_llm_profiles({"services": {}})


@pytest.mark.parametrize("url", ["http://public.example", "https://localhost", "https://127.0.0.1", "https://169.254.169.254", "https://user:pass@public.example", "https://public.example/?key=secret", "https://public.example:bad", "https://224.0.0.1"])
def test_endpoint_rejects_unsafe_addresses(store, url):
    from fastapi import HTTPException
    from integrations.deeptutor.heart_model_api import _check_endpoint
    with pytest.raises(HTTPException):
        _check_endpoint(url)


def test_endpoint_checks_all_dns_answers(store, monkeypatch):
    from fastapi import HTTPException
    from integrations.deeptutor.heart_model_api import _check_endpoint
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kw: [
        (2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("10.0.0.1", 443))])
    with pytest.raises(HTTPException):
        _check_endpoint("https://public.example")


def test_model_api_masks_and_deletes_without_vendor_files(store, monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from deeptutor.api.routers.auth import require_auth
    from integrations.deeptutor.heart_model_api import install_heart_model
    from deeptutor.multi_user import personal_models
    from deeptutor.services.llm import openai_http_client
    monkeypatch.setattr(openai_http_client, "_external_http_client", None)
    monkeypatch.setattr(personal_models, "_external_llm_profiles", None)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kw: [(2, 1, 6, "", ("8.8.8.8", 443))])
    app = FastAPI()
    app.dependency_overrides[require_auth] = lambda: SimpleNamespace(username="api-user", user_id="vendor-api")
    install_heart_model(app, tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/heart/model").json() == {"configured": False}
        assert client.get("/api/heart/evaluation").json() == {"enabled": True}
        assert client.put("/api/heart/evaluation", json={"enabled": False}).json() == {"enabled": False}
        assert client.put("/api/heart/evaluation", json={"enabled": "false"}).status_code == 422
        assert client.get("/api/heart/evaluation/jobs/nonexistent").status_code == 404
        listing = client.get("/api/heart/evaluation/jobs")
        assert listing.json() == {"jobs": []}
        assert listing.headers["cache-control"] == "no-store"
        response = client.put("/api/heart/model", json={"base_url": "https://public.example/v1", "model": "my-model", "api_key": "secret-api-key"})
        assert response.status_code == 200
        data = client.get("/api/heart/model").json()
        assert data["configured"] and "secret-api-key" not in str(data)
        assert data["model"] == "my-model"
        assert client.put("/api/heart/model", json={"base_url": "https://public.example", "model": " ", "api_key": " "}).status_code == 400
        assert list(tmp_path.iterdir()) == []
        assert client.delete("/api/heart/model").json() == {"configured": False}
        assert client.get("/api/heart/model").json() == {"configured": False}


def test_credential_versions_change_even_when_same_key_is_saved(store):
    _save_verified(store, "version-owner", "https://public.example/v1", "same-model", "same-key")
    first = store.read("version-owner")["credential_version"]
    _save_verified(store, "version-owner", "https://public.example/v1", "same-model", "same-key")
    second = store.read("version-owner")["credential_version"]
    assert first != second
    store.delete("version-owner")
    _save_verified(store, "version-owner", "https://public.example/v1", "same-model", "same-key")
    assert store.read("version-owner")["credential_version"] not in (first, second)


def test_pending_job_pauses_on_key_delete_and_resumes_with_new_configuration(store):
    from integrations.deeptutor import assessment_jobs as jobs
    owner = "queue-pause"
    _save_verified(store, owner, "https://public.example/v1", "old-model", "old-key")
    job = jobs.enqueue(owner, "vendor-pause", "answer-1", {"answer": "A"}, "rule-v1")
    claim = jobs.claim(owner)
    store.delete(owner)
    assert jobs.status(owner, job)["status"] == "paused"
    assert jobs.begin_send(owner, job, claim["lease_token"]) is None
    _save_verified(store, owner, "https://public.example/v1", "new-model", "new-key")
    new_claim = jobs.claim(owner)
    dispatch = jobs.begin_send(owner, job, new_claim["lease_token"])
    assert dispatch["config"]["api_key"] == "new-key"
    assert jobs.status(owner, job)["used_model"] == "new-model"
    assert jobs.status(owner, job)["rule_version"] == "rule-v1"
    assert jobs.status(owner, job)["credential_version"] == store.read(owner)["credential_version"]


def test_sent_job_keeps_only_in_memory_snapshot_and_accepts_result_after_disable(store, monkeypatch):
    from integrations.deeptutor import assessment_jobs as jobs
    from integrations.deeptutor.heart_model_api import _personal_profiles
    from deeptutor.multi_user.context import get_current_user, get_current_user_or_none
    from deeptutor.multi_user import paths
    from database.models import AssessmentJobRow
    monkeypatch.setattr(paths, "scope_for_user", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", ("8.8.8.8", port))])
    owner = "queue-sent"
    _save_verified(store, owner, "https://public.example/v1", "old-model", "old-key")
    job = jobs.enqueue(owner, "vendor-sent", "answer-2", {"answer": "B"}, "rule-v1")
    claim = jobs.claim(owner)
    dispatch = jobs.begin_send(owner, job, claim["lease_token"])
    previous = get_current_user_or_none()
    with jobs.execution_scope(dispatch):
        store.delete(owner)
        jobs.set_enabled(owner, False)
        _save_verified(store, owner, "https://public.example/v1", "new-model", "new-key")
        assert jobs.status(owner, job)["status"] == "sent"
        assert _personal_profiles(get_current_user())[0]["api_key"] == "old-key"
        with pytest.raises(RuntimeError, match="不属于"):
            store.runtime_config("someone-else")
    assert get_current_user_or_none() is previous
    assert store.runtime_config(owner)["api_key"] == "new-key"
    assert jobs.finish(owner, job, claim["lease_token"], {"vendor_result": "accepted"})
    assert jobs.finish(owner, job, claim["lease_token"], {"vendor_result": "accepted"})
    assert not jobs.finish(owner, job, claim["lease_token"], {"vendor_result": "changed"})
    with store.session_scope() as session:
        row = session.get(AssessmentJobRow, job)
        saved = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        assert "old-key" not in str(saved) and "new-key" not in str(saved)
        assert row.used_model == "old-model"


def test_disabled_evaluation_cancels_pending_and_never_backfills_off_period(store):
    from integrations.deeptutor import assessment_jobs as jobs
    from database.models import AssessmentJobRow
    owner = "queue-toggle"
    job = jobs.enqueue(owner, "vendor-toggle", "before-off", {"answer": "A"}, "rule-v1")
    jobs.set_enabled(owner, False)
    assert jobs.status(owner, job)["status"] == "cancelled"
    assert jobs.enqueue(owner, "vendor-toggle", "during-off", {"answer": "private answer"}, "rule-v1") is None
    jobs.set_enabled(owner, True)
    _save_verified(store, owner, "https://public.example/v1", "model", "key-toggle")
    assert jobs.status(owner, job)["status"] == "cancelled"
    assert jobs.enqueue(owner, "vendor-toggle", "during-off", {"answer": "private answer"}, "rule-v1") is None
    assert jobs.claim(owner) is None
    with store.session_scope() as session:
        from sqlalchemy import select
        tombstone = session.scalar(select(AssessmentJobRow).where(AssessmentJobRow.student_id == owner,
            AssessmentJobRow.source_id == "during-off"))
        assert tombstone.input == {}


def test_expired_claim_recovers_but_expired_send_never_automatically_retries(store):
    from datetime import timedelta
    from integrations.deeptutor import assessment_jobs as jobs
    owner = "queue-restart"
    _save_verified(store, owner, "https://public.example/v1", "model", "key-restart")
    job = jobs.enqueue(owner, "vendor-restart", "answer", {"answer": "C"}, "rule-v1")
    now = jobs._now()
    first = jobs.claim(owner, now=now)
    recovered = jobs.claim(owner, now=now + timedelta(seconds=91))
    assert recovered["id"] == first["id"] and recovered["lease_token"] != first["lease_token"]
    assert jobs.begin_send(owner, job, first["lease_token"], now=now + timedelta(seconds=91)) is None
    assert jobs.begin_send(owner, job, recovered["lease_token"], now=now + timedelta(seconds=91))
    assert jobs.claim(owner, now=now + timedelta(seconds=182)) is None
    assert jobs.status(owner, job)["status"] == "unknown"
    assert jobs.finish(owner, job, recovered["lease_token"], {"late": "result"})


def test_unknown_outcome_requires_explicit_retry_and_fences_old_attempt(store):
    from integrations.deeptutor import assessment_jobs as jobs
    owner = "queue-unknown"
    _save_verified(store, owner, "https://public.example/v1", "model", "key-unknown")
    job = jobs.enqueue(owner, "vendor-unknown", "answer", {"answer": "D"}, "rule-v1")
    first = jobs.claim(owner)
    jobs.begin_send(owner, job, first["lease_token"])
    assert jobs.fail(owner, job, first["lease_token"])
    assert jobs.claim(owner) is None
    assert not jobs.retry_unknown("other-owner", job)
    assert jobs.retry_unknown(owner, job)
    second = jobs.claim(owner)
    assert not jobs.finish(owner, job, first["lease_token"], {"late": "old"})
    assert jobs.begin_send(owner, job, second["lease_token"])
    assert jobs.finish(owner, job, second["lease_token"], {"fresh": "result"})


def test_only_explicit_rate_limit_is_retried_with_wait_and_attempt_limit(store):
    from datetime import timedelta
    from integrations.deeptutor import assessment_jobs as jobs
    owner = "queue-rate-limit"
    _save_verified(store, owner, "https://public.example/v1", "model", "key-rate")
    job = jobs.enqueue(owner, "vendor-rate", "answer", {"answer": "E"}, "rule-v1")
    for attempt in range(jobs.MAX_ATTEMPTS):
        now = jobs._now() + timedelta(hours=attempt)
        claim = jobs.claim(owner, now=now)
        assert jobs.begin_send(owner, job, claim["lease_token"], now=now)
        assert jobs.fail(owner, job, claim["lease_token"], rate_limited=True, retry_after=120)
        if attempt == 0:
            assert jobs.claim(owner) is None
    assert jobs.status(owner, job)["status"] == "failed"
    store.delete(owner)
    _save_verified(store, owner, "https://public.example/v1", "model", "new-key-rate")
    assert jobs.status(owner, job)["status"] == "failed"


def test_queue_idempotency_owner_isolation_and_single_concurrent_claim(store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from integrations.deeptutor import assessment_jobs as jobs
    owner = "queue-concurrent"
    _save_verified(store, owner, "https://public.example/v1", "model", "key-concurrent")
    first = jobs.enqueue(owner, "vendor-concurrent", "answer-1", {"answer": "F"}, "rule-v1")
    assert jobs.enqueue(owner, "vendor-concurrent", "answer-1", {"answer": "F"}, "rule-v1") == first
    with pytest.raises(ValueError, match="conflict"):
        jobs.enqueue(owner, "vendor-concurrent", "answer-1", {"answer": "different"}, "rule-v1")
    jobs.enqueue(owner, "vendor-concurrent", "answer-2", {"answer": "G"}, "rule-v1")
    assert jobs.status("other-owner", first) is None
    barrier = Barrier(2)
    def worker():
        barrier.wait()
        return jobs.claim(owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: worker(), range(2)))
    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert jobs.begin_send("other-owner", claimed[0]["id"], claimed[0]["lease_token"]) is None


def test_credential_and_queue_changes_roll_back_together(store, monkeypatch):
    from integrations.deeptutor import assessment_jobs as jobs
    owner = "queue-atomic"
    _save_verified(store, owner, "https://public.example/v1", "old-model", "old-atomic-key")
    version = store.read(owner)["credential_version"]
    job = jobs.enqueue(owner, "vendor-atomic", "answer", {"answer": "H"}, "rule-v1")
    def broken(*args, **kwargs):
        raise RuntimeError("test transaction failure")
    monkeypatch.setattr(jobs, "credentials_changed", broken)
    with pytest.raises(RuntimeError):
        _save_verified(store, owner, "https://public.example/v1", "new-model", "new-atomic-key")
    assert store.read(owner)["credential_version"] == version
    with pytest.raises(RuntimeError):
        store.delete(owner)
    assert store.read(owner, decrypt=True)["api_key"] == "old-atomic-key"
    assert jobs.status(owner, job)["status"] == "queued"


def test_key_delete_and_send_boundary_are_serialized(store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from integrations.deeptutor import assessment_jobs as jobs
    owner = "queue-delete-race"
    _save_verified(store, owner, "https://public.example/v1", "race-model", "race-key")
    job = jobs.enqueue(owner, "vendor-race", "answer", {"answer": "I"}, "rule-v1")
    claim = jobs.claim(owner)
    barrier = Barrier(2)
    def delete_key():
        barrier.wait()
        store.delete(owner)
    def send():
        barrier.wait()
        return jobs.begin_send(owner, job, claim["lease_token"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleted = pool.submit(delete_key)
        dispatch = pool.submit(send)
        deleted.result()
        snapshot = dispatch.result()
    assert store.read(owner) is None
    if snapshot is None:
        assert jobs.status(owner, job)["status"] == "paused"
    else:
        assert jobs.status(owner, job)["status"] == "sent"
        assert snapshot["config"]["api_key"] == "race-key"


def _scoring_input():
    return {"session_id": "session-score", "turn_id": "turn-score", "message_id": "1",
            "answer": "自变量是研究者操纵的变量。", "workspace_id": "source-workspace",
            "history": [], "catalog_version": "registry-test",
            "mastery_path_id": "path-score", "independent": False,
            "targets": [{"id": "kc-1-1", "name": "自变量", "type": "concept", "source_ids": ["evidence-1"]}],
            "sources": [{"id": "evidence-1", "text": "自变量是研究者操纵的变量。", "document_id": "book", "version": "v1"}]}


def _judgment(**updates):
    result = {"assessable": True, "knowledge_point_id": "kc-1-1", "passed": True,
              "feedback": "解释与教材定义一致。", "answer_excerpt": "研究者操纵的变量",
              "citations": [{"source_id": "evidence-1", "quote": "研究者操纵的变量"}]}
    result.update(updates)
    import json
    return json.dumps(result, ensure_ascii=False)


def _queue_scoring(store, monkeypatch, owner):
    from integrations.deeptutor import assessment_jobs as jobs, assessment_worker as worker
    from deeptutor.multi_user import paths
    monkeypatch.setattr(paths, "scope_for_user", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(worker, "confirmed_catalog", lambda: ({"kc-1-1": {}}, "registry-test"))
    _save_verified(store, owner, "https://public.example/v1", "model-score", "key-score")
    job = jobs.enqueue(owner, "vendor-" + owner, "score-answer", _scoring_input(), worker.RULE_VERSION)
    return jobs, worker, job


def _saved_result(store, job):
    from database.models import AssessmentJobRow
    with store.session_scope() as session:
        return session.get(AssessmentJobRow, job).result


def test_scoring_consumer_saves_grounded_result_without_publishing_mastery(store, monkeypatch):
    import asyncio
    jobs, worker, job = _queue_scoring(store, monkeypatch, "score-success")
    calls = []
    async def judge(dispatch, correction=""):
        calls.append(correction)
        assert store.runtime_config(dispatch["student_id"])["api_key"] == "key-score"
        return _judgment()
    monkeypatch.setattr(worker, "judge", judge)
    assert asyncio.run(worker.run_one("score-success"))
    assert jobs.status("score-success", job)["status"] == "completed"
    result = _saved_result(store, job)
    assert result["publication_status"] == "pending" and result["independent"] is False
    assert result["judgment"]["passed"] is True and result["model_responses"] == 1
    assert calls == [""] and "key-score" not in str(result)


def test_attribution_repaired_only_once_then_discarded(store, monkeypatch):
    import asyncio
    jobs, worker, job = _queue_scoring(store, monkeypatch, "score-bad-id")
    calls = []
    async def judge(dispatch, correction=""):
        calls.append(correction)
        return _judgment(knowledge_point_id="invented-id")
    monkeypatch.setattr(worker, "judge", judge)
    asyncio.run(worker.run_one("score-bad-id"))
    assert len(calls) == 2 and calls[1] == "knowledge_point_mismatch"
    assert jobs.status("score-bad-id", job)["status"] == "discarded"
    assert not asyncio.run(worker.run_one("score-bad-id"))


def test_fabricated_textbook_quote_discards_without_extra_model_call(store, monkeypatch):
    import asyncio
    jobs, worker, job = _queue_scoring(store, monkeypatch, "score-bad-quote")
    calls = []
    async def judge(dispatch, correction=""):
        calls.append(correction)
        return _judgment(citations=[{"source_id": "evidence-1", "quote": "教材中不存在这段原文"}])
    monkeypatch.setattr(worker, "judge", judge)
    asyncio.run(worker.run_one("score-bad-quote"))
    assert calls == [""] and jobs.status("score-bad-quote", job)["status"] == "discarded"


def test_catalog_change_discards_before_model_call(store, monkeypatch):
    import asyncio
    jobs, worker, job = _queue_scoring(store, monkeypatch, "score-catalog")
    monkeypatch.setattr(worker, "confirmed_catalog", lambda: ({}, ""))
    async def forbidden(*args):
        pytest.fail("unconfirmed catalog must not invoke model")
    monkeypatch.setattr(worker, "judge", forbidden)
    asyncio.run(worker.run_one("score-catalog"))
    assert jobs.status("score-catalog", job)["last_error"] == "catalog_or_rule_changed"


def test_repair_rate_limit_resumes_repair_without_repeating_initial_assessment(store, monkeypatch):
    import asyncio
    from datetime import timedelta
    from database.models import AssessmentJobRow
    jobs, worker, job = _queue_scoring(store, monkeypatch, "score-repair-rate")
    calls = []
    class RateLimited(Exception):
        status_code = 429
        response = SimpleNamespace(headers={"retry-after": "1"})
    async def judge(dispatch, correction=""):
        calls.append(correction)
        if len(calls) == 1:
            return _judgment(knowledge_point_id="wrong")
        if len(calls) == 2:
            raise RateLimited()
        return _judgment()
    monkeypatch.setattr(worker, "judge", judge)
    asyncio.run(worker.run_one("score-repair-rate"))
    assert jobs.status("score-repair-rate", job)["status"] == "queued"
    assert _saved_result(store, job)["stage"] == "attribution_repair"
    with store.session_scope(immediate=True) as session:
        session.get(AssessmentJobRow, job).ready_at = jobs._now() - timedelta(seconds=1)
    _save_verified(store, "score-repair-rate", "https://public.example/v1", "replacement-model", "replacement-key")
    asyncio.run(worker.run_one("score-repair-rate"))
    assert calls == ["", "knowledge_point_mismatch", "knowledge_point_mismatch"]
    result = _saved_result(store, job)
    assert result["model_responses"] == 2 and result["initial_model"] == "model-score"
    assert jobs.status("score-repair-rate", job)["used_model"] == "replacement-model"


def test_model_timeout_leaves_unknown_and_does_not_blindly_retry(store, monkeypatch):
    import asyncio
    jobs, worker, job = _queue_scoring(store, monkeypatch, "score-timeout")
    async def judge(*args):
        raise TimeoutError()
    monkeypatch.setattr(worker, "judge", judge)
    asyncio.run(worker.run_one("score-timeout"))
    assert jobs.status("score-timeout", job)["status"] == "unknown"
    assert not asyncio.run(worker.run_one("score-timeout"))


def test_intake_requires_confirmed_exact_catalog_and_verified_textbook_sources(store, monkeypatch):
    import asyncio
    from integrations.deeptutor import assessment_intake as intake
    from deeptutor.learning import storage
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.learning.models import KnowledgeType
    from deeptutor.services.workspace import context as workspace_scopes
    monkeypatch.setattr(workspace_scopes, "current_workspace_id", lambda: "origin-workspace")
    point = SimpleNamespace(id="kc-1-1", type=KnowledgeType.CONCEPT)
    progress = SimpleNamespace(modules=[SimpleNamespace(knowledge_points=[point])])
    monkeypatch.setattr(storage, "LearningStore", lambda: SimpleNamespace(load=lambda path: progress, list_events=lambda path: []))
    canonical = {"kc-1-1": {"name": "自变量", "chapter_id": 1, "section_id": 1}}
    monkeypatch.setattr(intake, "confirmed_catalog", lambda: (canonical, "registry-test"))
    execution = SimpleNamespace(payload={"content": "自变量是研究者操纵的变量。"}, session_id="intake-session", turn_id="intake-turn")
    context = SimpleNamespace(attachments=[], metadata={"mastery_path_id": "path"}, conversation_history=[])
    source = {"type": "heart_textbook_evidence", "source_id": "evidence-1", "document_id": "book",
              "version": "v1", "quote": "研究者操纵的变量", "text": "自变量是研究者操纵的变量。",
              "chapter_id": 1, "section_id": 1,
              "location": {"evidence": {"evidence_id": "evidence-1", "document_version": "v1"}}}
    events = [{"metadata": {"sources": [source]}}]
    token = set_current_user(SimpleNamespace(id="vendor-intake", username="intake-owner", is_admin=False))
    try:
        candidate = intake.build_snapshot(execution, context, events, 10)
        assert candidate[3]["targets"][0]["id"] == "kc-1-1"
        assert candidate[3]["workspace_id"] == "origin-workspace"
        from dataclasses import replace
        from integrations.deeptutor.screenshot_intake import ScreenshotReading, ScreenshotReceipt
        reading = ScreenshotReading(question_count=1, question="请解释自变量", options={}, question_complete=True,
            student_answer="图中学生作答", answer_origin="student", reference_answer="参考答案不能混入作答", solution_steps="", missing_fields=[])
        receipt = ScreenshotReceipt("intake-owner", "vendor-intake", "intake-session", "intake-turn", "image-hash", "vision-model", "vision-version", reading)
        context.attachments = [SimpleNamespace(type="image")]
        context.extension_state = {"heart_screenshot": {"receipt": receipt}}
        image_candidate = intake.build_snapshot(execution, context, events, 10)
        assert "图中学生作答" in image_candidate[3]["answer"]
        assert "参考答案不能混入作答" not in image_candidate[3]["answer"]
        assert image_candidate[3]["screenshot"]["input_hash"] == "image-hash"
        assert image_candidate[3]["assistance"]["kc-1-1"]["status"] == "assisted"
        assert image_candidate[3]["independent"] is False
        context.extension_state["heart_screenshot"]["receipt"] = replace(receipt, turn_id="other-turn")
        assert intake.build_snapshot(execution, context, events, 10) is None
        context.extension_state = {}
        assert intake.build_snapshot(execution, context, events, 10) is None
        context.attachments = []
        asyncio.run(intake.completed_turn(execution, context, events, 10))
        source["section_id"] = 99
        assert intake.build_snapshot(execution, context, events, 11) is None
        source["section_id"] = 1
        source["location"]["evidence"]["document_version"] = "tampered"
        assert intake.build_snapshot(execution, context, events, 11) is None
        monkeypatch.setattr(intake, "confirmed_catalog", lambda: ({}, ""))
        assert intake.build_snapshot(execution, context, events, 11) is None
    finally:
        reset_current_user(token)


def test_background_slot_is_shared_across_connections(store):
    from integrations.deeptutor.assessment_worker import background_slot
    with background_slot() as first:
        assert first
        with background_slot() as second:
            assert not second
    with background_slot() as after:
        assert after


def test_worker_defers_when_foreground_busy_or_account_identity_changed(store, monkeypatch, tmp_path):
    import asyncio
    from integrations.deeptutor import assessment_worker as worker
    from deeptutor.api.routers import auth
    from deeptutor.multi_user import paths
    from deeptutor.services import session, workspace
    from deeptutor.services.workspace import context as workspace_scopes
    from contextlib import contextmanager
    selected = []
    @contextmanager
    def scoped(workspace_id):
        selected.append(workspace_id)
        try:
            yield
        finally:
            selected.pop()
    monkeypatch.setattr(workspace_scopes, "workspace_context", scoped)
    monkeypatch.setattr(workspace, "get_content_workspace_service", lambda: SimpleNamespace(
        list_workspaces=lambda: [{"kind": "workspace", "workspace_id": "other"}]))
    account = {"id": "vendor-current", "role": "student", "disabled": False}
    monkeypatch.setattr(auth, "get_user_info", lambda _: account)
    monkeypatch.setattr(paths, "scope_for_user", lambda *args, **kw: SimpleNamespace(root=tmp_path))
    active = []
    async def nonterminal():
        return active if selected[-1] == "other" else []
    monkeypatch.setattr(session, "get_session_store", lambda: SimpleNamespace(list_nonterminal_turns=nonterminal))
    assert not asyncio.run(worker.foreground_busy("owner", "vendor-current"))
    active.append({"status": "running"})
    assert asyncio.run(worker.foreground_busy("owner", "vendor-current"))
    active.clear()
    account["disabled"] = True
    assert asyncio.run(worker.foreground_busy("owner", "vendor-current"))
    account["disabled"] = False
    assert asyncio.run(worker.foreground_busy("owner", "vendor-old"))


def test_worker_lifespan_starts_after_app_and_cancels_cleanly(store, monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager
    from integrations.deeptutor import assessment_worker as worker
    from deeptutor.services.session.turns import executor
    events = []
    @asynccontextmanager
    async def original(app):
        events.append("app-start")
        yield {"ready": True}
        events.append("app-stop")
    async def loop():
        events.append("worker-start")
        try:
            await asyncio.Event().wait()
        finally:
            events.append("worker-stop")
    monkeypatch.setattr(worker, "worker_loop", loop)
    monkeypatch.setattr(executor, "_completion_observer", None)
    app = SimpleNamespace(router=SimpleNamespace(lifespan_context=original))
    worker.install_assessment_worker(app)
    async def run():
        async with app.router.lifespan_context(app) as state:
            assert state == {"ready": True}
            await asyncio.sleep(0)
    asyncio.run(run())
    assert events == ["app-start", "worker-start", "worker-stop", "app-stop"]
    assert executor._completion_observer is worker.completed_turn


def test_quota_error_is_not_retried_as_temporary_rate_limit(store, monkeypatch):
    import asyncio
    jobs, worker, job = _queue_scoring(store, monkeypatch, "score-quota")
    class QuotaError(Exception):
        status_code = 429
        code = "insufficient_quota"
        response = SimpleNamespace(headers={"retry-after": "1"})
    async def judge(*args):
        raise QuotaError()
    monkeypatch.setattr(worker, "judge", judge)
    asyncio.run(worker.run_one("score-quota"))
    assert jobs.status("score-quota", job)["status"] == "paused"
    assert jobs.status("score-quota", job)["last_error"] == "quota_exhausted"
    assert not asyncio.run(worker.run_one("score-quota"))


def test_catalog_loader_rejects_candidate_and_only_returns_confirmed_points(store, monkeypatch, tmp_path):
    import json
    from integrations.deeptutor import assessment_intake as intake
    path = tmp_path / "catalog.json"
    monkeypatch.setattr(intake, "REGISTRY", path)
    value = {"course_id": "experimental-psychology-3", "status": "candidate",
             "knowledge_components": [{"id": "kc-1-1", "status": "confirmed"}]}
    path.write_text(json.dumps(value), encoding="utf-8")
    assert intake.confirmed_catalog() == ({}, "")
    value["status"] = "confirmed"
    value["knowledge_components"].append({"id": "candidate-only", "status": "candidate"})
    path.write_text(json.dumps(value), encoding="utf-8")
    catalog, version = intake.confirmed_catalog()
    assert set(catalog) == {"kc-1-1"} and len(version) == 64
    path.write_text("[]", encoding="utf-8")
    assert intake.confirmed_catalog() == ({}, "")


@pytest.fixture
def publication_env(store, monkeypatch, tmp_path):
    import asyncio
    from contextlib import contextmanager
    from database.models import Base, Student, MisconceptionRow, EvidenceRow, LearningEventRow, EventEvidenceRow
    from deeptutor.learning import storage
    from deeptutor.learning.models import LearningProgress, LearningModule, KnowledgePoint, KnowledgeType
    from deeptutor.services import session
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from deeptutor.services.workspace import context as scopes
    from deeptutor.api.routers import auth
    from deeptutor.multi_user import paths
    from integrations.deeptutor import assessment_jobs as publication_jobs
    publication_jobs.set_enabled("publisher", True)
    jobs, worker, job = _queue_scoring(store, monkeypatch, "publisher")
    Base.metadata.create_all(store.engine, tables=[Student.__table__, MisconceptionRow.__table__,
        EvidenceRow.__table__, LearningEventRow.__table__, EventEvidenceRow.__table__])
    learning = storage.LearningStore(tmp_path / "learning")
    learning.save(LearningProgress(book_id="path-score", modules=[LearningModule(id="m", name="教材节", order=0,
        knowledge_points=[KnowledgePoint(id="kc-1-1", name="自变量", type=KnowledgeType.CONCEPT, module_id="m")])],
        knowledge_types={"kc-1-1": KnowledgeType.CONCEPT}))
    monkeypatch.setattr(storage, "LearningStore", lambda: learning)
    notebook = SQLiteSessionStore(db_path=tmp_path / "notebook.db")
    asyncio.run(notebook.create_session(title="S", session_id="session-score"))
    monkeypatch.setattr(session, "get_sqlite_session_store", lambda: notebook)
    monkeypatch.setattr(paths, "scope_for_user", lambda *args, **kw: SimpleNamespace(root=tmp_path))
    account = {"id": "vendor-publisher", "role": "student", "disabled": False}
    monkeypatch.setattr(auth, "get_user_info", lambda _: account)
    selected = []
    @contextmanager
    def scoped(workspace_id):
        selected.append(workspace_id)
        yield
    monkeypatch.setattr(scopes, "workspace_context", scoped)
    async def judge(*args):
        return _judgment()
    monkeypatch.setattr(worker, "judge", judge)
    asyncio.run(worker.run_one("publisher"))
    yield SimpleNamespace(jobs=jobs, job=job, learning=learning, notebook=notebook, selected=selected,
                          account=account, store=store, monkeypatch=monkeypatch, worker=worker)
    from database.models import AssessmentJobRow
    from sqlalchemy import select
    with store.session_scope(immediate=True) as session:
        for child in session.scalars(select(AssessmentJobRow).where(jobs.REASSESSMENT_ROOT == job)).all():
            session.delete(child)
        student = session.get(Student, "publisher")
        if student is not None:
            session.delete(student)
        session.delete(session.get(AssessmentJobRow, job))
    jobs.set_enabled("publisher", True)


def test_publish_result_once_without_key_and_without_promoting_unverified_mastery(publication_env):
    import asyncio
    from sqlalchemy import select, func
    from database.models import EvidenceRow, EventEvidenceRow, LearningEventRow
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    env.store.delete("publisher")
    env.jobs.set_enabled("publisher", False)
    assert ("publisher", "vendor-publisher", env.job) in env.jobs.pending_publications()
    assert asyncio.run(publish_one("publisher", env.job))
    assert not asyncio.run(publish_one("publisher", env.job))
    progress = env.learning.load("path-score")
    assert len(progress.learning_evidence) == 1 and not progress.qualitative_mastery
    assert not progress.repetition_states and not progress.review_queue
    evidence = progress.learning_evidence[0]
    assert evidence.visual_context["independent"] is False
    assert evidence.visual_context["judgment"]["passed"] is True
    attempt = asyncio.run(env.notebook.get_assessment_attempt(evidence.evidence_id))
    assert attempt["visual_context"]["independent"] is False
    assert attempt["result"] == "correct"
    with env.store.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceRow)) == 1
        linked = session.scalar(select(EventEvidenceRow))
        assert not linked.independent and linked.verification == "vendor_recorded"
        payload = session.scalar(select(LearningEventRow)).payload
        assert payload["assessed_mastered"] is False and payload["retention"] is None
    assert env.jobs.status("publisher", env.job)["publication_status"] == "published"
    assert env.selected == ["source-workspace"]


def test_sync_failure_rolls_back_h_and_retry_reuses_vendor_evidence(publication_env, monkeypatch):
    import asyncio
    from sqlalchemy import select, func
    from database.models import EvidenceRow, LearningEventRow
    from database.repository import Repository
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    original = Repository.add_event_evidence
    def fail_after_insert(self, *args, **kw):
        original(self, *args, **kw)
        raise RuntimeError("simulated PG write failure")
    monkeypatch.setattr(Repository, "add_event_evidence", fail_after_insert)
    assert not asyncio.run(publish_one("publisher", env.job))
    with env.store.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceRow)) == 0
        assert session.scalar(select(func.count()).select_from(LearningEventRow)) == 0
    assert len(env.learning.load("path-score").learning_evidence) == 1
    assert env.jobs.status("publisher", env.job)["publication_status"] == "pending"
    assert ("publisher", "vendor-publisher", env.job) not in env.jobs.pending_publications()
    from database.models import AssessmentJobRow
    from datetime import timedelta
    with env.store.session_scope(immediate=True) as session:
        session.get(AssessmentJobRow, env.job).ready_at = env.jobs._now() - timedelta(seconds=1)
    assert ("publisher", "vendor-publisher", env.job) in env.jobs.pending_publications()
    monkeypatch.setattr(Repository, "add_event_evidence", original)
    async def forbidden(*args):
        pytest.fail("publication retries must never invoke model")
    monkeypatch.setattr(env.worker, "judge", forbidden)
    assert asyncio.run(publish_one("publisher", env.job))
    assert len(env.learning.load("path-score").learning_evidence) == 1
    with env.store.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceRow)) == 1


def test_notebook_failure_retries_without_duplicate_path_evidence(publication_env, monkeypatch):
    import asyncio
    from deeptutor.learning import assessment
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    original = assessment.record_assessment
    async def failed(*args):
        raise RuntimeError("simulated notebook failure")
    monkeypatch.setattr(assessment, "record_assessment", failed)
    assert not asyncio.run(publish_one("publisher", env.job))
    assert len(env.learning.load("path-score").learning_evidence) == 1
    monkeypatch.setattr(assessment, "record_assessment", original)
    assert asyncio.run(publish_one("publisher", env.job))
    assert len(env.learning.load("path-score").learning_evidence) == 1


def test_publication_rejects_rebound_identity_and_malformed_saved_result(publication_env):
    import asyncio
    from database.models import AssessmentJobRow
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    env.account["id"] = "another-vendor-id"
    assert not asyncio.run(publish_one("publisher", env.job))
    assert not env.learning.load("path-score").learning_evidence
    env.account["id"] = "vendor-publisher"
    with env.store.session_scope(immediate=True) as session:
        row = session.get(AssessmentJobRow, env.job)
        row.result = {**row.result, "judgment": {**row.result["judgment"], "knowledge_point_id": "other-point"}}
    assert not asyncio.run(publish_one("publisher", env.job))
    assert not env.learning.load("path-score").learning_evidence
    assert env.jobs.status("publisher", env.job)["publication_status"] == "blocked"


@pytest.mark.parametrize("teaching_order,expected", [("before", "assisted"), ("after", "not_verified"), ("none", "not_verified")])
def test_assistance_uses_committed_event_order_not_missing_flags_or_clock(store, tmp_path, teaching_order, expected):
    from integrations.deeptutor.assessment_intake import assistance_for_turn
    from deeptutor.learning.storage import LearningStore
    from deeptutor.learning.service import LearningService
    from deeptutor.learning.models import LearningProgress, LearningModule, KnowledgePoint, KnowledgeType, PendingQuestion
    learning = LearningStore(tmp_path / "assistance")
    learning.save(LearningProgress(book_id="ordered-path", modules=[LearningModule(id="m", name="教材节", order=0,
        knowledge_points=[KnowledgePoint(id="kc-1-1", name="自变量", type=KnowledgeType.CONCEPT, module_id="m")])]))
    service = LearningService(learning)
    service.register_question("ordered-path", PendingQuestion(question_id="ordered-question", knowledge_point_id="kc-1-1",
        prompt="请解释自变量", expected_answer="研究者操纵的变量"), session_id="ordered-session", turn_id="question-turn")
    def teach(tx):
        tx.emit("objective.explained", {"knowledge_point_id": "kc-1-1", "summary": "讲解"})
    if teaching_order == "before":
        learning.mutate("ordered-path", teach)
    service.record_question_answer("ordered-path", "研究者操纵的变量", interaction_id="ordered-question",
                                  session_id="ordered-session", turn_id="answer-turn")
    if teaching_order == "after":
        learning.mutate("ordered-path", teach)
    execution = SimpleNamespace(session_id="ordered-session", turn_id="answer-turn")
    state = assistance_for_turn(learning, "ordered-path", execution, "研究者操纵的变量", {"kc-1-1": {}})["kc-1-1"]
    assert state["status"] == expected and state["coverage"] == "partial"
    assert state["question_id"] == "ordered-question"
    assert state["events"][0]["type"] == "interaction.registered"
    assert state["events"][-1]["type"] == "interaction.answered"
    assert [event["id"] for event in state["events"]] == sorted(event["id"] for event in state["events"])
    assert assistance_for_turn(learning, "ordered-path", execution, "别人的作答", {"kc-1-1": {}})["kc-1-1"]["events"] == []
    execution.session_id = "other-session"
    assert assistance_for_turn(learning, "ordered-path", execution, "研究者操纵的变量", {"kc-1-1": {}})["kc-1-1"]["status"] == "not_verified"


def test_recent_assessments_are_bounded_owner_bound_and_never_expose_snapshots(store):
    import json
    from integrations.deeptutor import assessment_jobs as jobs
    snapshot = _scoring_input()
    snapshot["history"] = [{"role": "user", "content": "private-history-not-for-list"}]
    snapshot["secret_extra"] = "private-extra-not-for-list"
    for i in range(25):
        jobs.enqueue("list-owner", "list-vendor", "listed-" + str(i), snapshot, "rule-list")
    jobs.enqueue("other-list-owner", "other-vendor", "other-listed", snapshot, "rule-list")
    jobs.enqueue("list-owner", "rebound-vendor", "rebound-listed", snapshot, "rule-list")
    listed = jobs.recent_jobs("list-owner", "list-vendor")
    assert len(listed["jobs"]) == 20
    assert all(item["knowledge_point"] == "自变量" and item["passed"] is None for item in listed["jobs"])
    encoded = json.dumps(listed)
    assert "private-history-not-for-list" not in encoded and "private-extra-not-for-list" not in encoded
    assert "vendor_user_id" not in encoded and "credential_version" not in encoded
    assert jobs.recent_jobs("missing-list-owner", "list-vendor") == {"jobs": []}
    assert len(jobs.recent_jobs("list-owner", "rebound-vendor")["jobs"]) == 1
    job = listed["jobs"][0]["id"]
    assert jobs.status("list-owner", job, "rebound-vendor") is None


def test_assisted_publication_preserves_order_and_does_not_claim_independent(publication_env):
    from integrations.deeptutor.assessment_publication import publish_to_path
    env = publication_env
    dispatch = env.jobs.publication("publisher", env.job)
    assistance = {"status": "assisted", "coverage": "partial", "question_id": "q",
        "events": [{"id": 1, "type": "interaction.registered"}, {"id": 2, "type": "objective.explained"},
                   {"id": 3, "type": "interaction.answered"}]}
    dispatch["input"]["assistance"] = {"kc-1-1": assistance}
    receipt = publish_to_path(dispatch)
    evidence = receipt["assessment"]
    assert evidence["hints_used"] == 1 and evidence["visual_context"]["independent"] is False
    assert evidence["visual_context"]["assistance"] == assistance
    assert not receipt["assessed_mastered"] and receipt["learning_stage"] == "practiced_with_help"



def _published_for_reassessment(env, monkeypatch):
    import asyncio
    from integrations.deeptutor import assessment_intake as intake
    from integrations.deeptutor.assessment_publication import publish_one
    monkeypatch.setattr(intake, "confirmed_catalog", lambda: ({"kc-1-1": {}}, "registry-test"))
    assert asyncio.run(publish_one("publisher", env.job))


def test_reassessment_is_idempotent_independent_of_auto_switch_and_preserves_both_results(publication_env, monkeypatch):
    import asyncio
    from uuid import uuid4
    from concurrent.futures import ThreadPoolExecutor
    from database.models import AssessmentJobRow
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    _published_for_reassessment(env, monkeypatch)
    env.jobs.set_enabled("publisher", False)
    request_id = str(uuid4())
    def request():
        return env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, request_id, "请核对概念边界", confirm_cost=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request(), range(2)))
    child = responses[0]["id"]
    assert child == responses[1]["id"] and responses[0]["already_submitted"] != responses[1]["already_submitted"]
    env.jobs.set_enabled("publisher", False)
    assert env.jobs.status("publisher", child)["status"] == "queued"
    env.store.delete("publisher")
    assert env.jobs.status("publisher", child)["status"] == "paused"
    _save_verified(env.store, "publisher", "https://public.example/v1", "review-model", "review-key")
    assert env.jobs.status("publisher", child)["status"] == "queued"
    calls = []
    async def judge(dispatch, correction=""):
        calls.append(dispatch["input"]["reassessment"])
        assert len(dispatch["input"]["targets"]) == 1
        return _judgment(passed=False, feedback="复评后调整：原作答未完整说明概念边界。")
    monkeypatch.setattr(env.worker, "judge", judge)
    assert asyncio.run(env.worker.run_one("publisher"))
    assert len(calls) == 1 and calls[0]["previous_judgment"]["passed"] is True
    assert asyncio.run(publish_one("publisher", child))
    assert request()["id"] == child
    with pytest.raises(ValueError, match="already_succeeded"):
        env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "再次核查", confirm_cost=True)
    with env.store.session_scope() as session:
        original = session.get(AssessmentJobRow, env.job)
        assert original.result["judgment"]["passed"] is True
        assert original.result["effective_reassessment_id"] == child
    progress = env.learning.load("path-score")
    assert len(progress.learning_evidence) == 2 and not progress.qualitative_mastery
    assert progress.learning_evidence[1].visual_context["supersedes_evidence_id"] == progress.learning_evidence[0].evidence_id
    listing = env.jobs.recent_jobs("publisher", "vendor-publisher")["jobs"]
    assert len(listing) == 1 and listing[0]["passed"] is True
    assert listing[0]["reassessment"]["passed"] is False and listing[0]["reassessment"]["effective"]
    assert not listing[0]["reassessment"]["can_retry"]


def test_reassessment_unknown_requires_explicit_new_cost_confirmation_and_fences_late_result(publication_env, monkeypatch):
    from uuid import uuid4
    env = publication_env
    _published_for_reassessment(env, monkeypatch)
    request_id = str(uuid4())
    old = env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, request_id, "核查", confirm_cost=True)["id"]
    claim = env.jobs.claim("publisher")
    env.jobs.begin_send("publisher", old, claim["lease_token"])
    env.jobs.fail("publisher", old, claim["lease_token"])
    with pytest.raises(ValueError, match="outcome_unknown"):
        env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "核查", confirm_cost=True)
    assert env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, request_id, "核查", confirm_cost=True)["id"] == old
    new = env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "核查", confirm_cost=True, confirm_unknown_retry=True)
    assert new["id"] != old
    assert env.jobs.status("publisher", old)["status"] == "superseded"
    assert not env.jobs.finish("publisher", old, claim["lease_token"], {"late": "result"})


def test_failed_reassessment_keeps_request_idempotent_and_allows_explicit_new_application(publication_env, monkeypatch):
    from uuid import uuid4
    env = publication_env
    _published_for_reassessment(env, monkeypatch)
    request_id = str(uuid4())
    first = env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, request_id, "核查", confirm_cost=True)["id"]
    claim = env.jobs.claim("publisher")
    env.jobs.begin_send("publisher", first, claim["lease_token"])
    env.jobs.discard("publisher", first, claim["lease_token"])
    assert env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, request_id, "核查", confirm_cost=True)["id"] == first
    second = env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "补充复评理由", confirm_cost=True)["id"]
    assert second != first
    concurrent = env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "另一申请", confirm_cost=True)
    assert concurrent["id"] == second and concurrent["already_submitted"]


def test_reassessment_rejects_owner_fee_and_version_mismatches_before_queueing(publication_env, monkeypatch):
    from uuid import uuid4
    from integrations.deeptutor import assessment_intake as intake
    env = publication_env
    kwargs = dict(confirm_cost=True)
    with pytest.raises(ValueError, match="not_published"):
        env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "核查", **kwargs)
    _published_for_reassessment(env, monkeypatch)
    with pytest.raises(ValueError, match="cost_confirmation"):
        env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "核查", confirm_cost=False)
    with pytest.raises(ValueError, match="not_found"):
        env.jobs.request_reassessment("publisher", "rebound-vendor", env.job, str(uuid4()), "核查", **kwargs)
    from database.models import AssessmentJobRow
    with env.store.session_scope(immediate=True) as session:
        row = session.get(AssessmentJobRow, env.job)
        row.result = {**row.result, "independent": True}
    with pytest.raises(ValueError, match="qualification_unsupported"):
        env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "核查", **kwargs)
    with env.store.session_scope(immediate=True) as session:
        row = session.get(AssessmentJobRow, env.job)
        row.result = {**row.result, "independent": False}
    monkeypatch.setattr(intake, "confirmed_catalog", lambda: ({"kc-1-1": {}}, "new-catalog"))
    with pytest.raises(ValueError, match="catalog_changed"):
        env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "核查", **kwargs)


def test_reassessment_publication_retry_never_rejudges_and_only_then_updates_effective_link(publication_env, monkeypatch):
    import asyncio
    from uuid import uuid4
    from database.repository import Repository
    from database.models import AssessmentJobRow
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    _published_for_reassessment(env, monkeypatch)
    child = env.jobs.request_reassessment("publisher", "vendor-publisher", env.job, str(uuid4()), "核查", confirm_cost=True)["id"]
    assert asyncio.run(env.worker.run_one("publisher"))
    original = Repository.add_event_evidence
    def failed(*args, **kwargs):
        raise RuntimeError("temporary sync failure")
    monkeypatch.setattr(Repository, "add_event_evidence", failed)
    assert not asyncio.run(publish_one("publisher", child))
    with env.store.session_scope() as session:
        assert "effective_reassessment_id" not in session.get(AssessmentJobRow, env.job).result
    monkeypatch.setattr(Repository, "add_event_evidence", original)
    async def forbidden(*args):
        pytest.fail("publication must never rejudge")
    monkeypatch.setattr(env.worker, "judge", forbidden)
    assert asyncio.run(publish_one("publisher", child))
    assert len(env.learning.load("path-score").learning_evidence) == 2


def test_reassessment_api_requires_fee_confirmation_and_rejects_client_grades(publication_env, monkeypatch, tmp_path):
    from uuid import uuid4
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from deeptutor.api.routers.auth import require_auth
    from deeptutor.multi_user import personal_models
    from deeptutor.services.llm import openai_http_client
    from integrations.deeptutor.heart_model_api import install_heart_model
    env = publication_env
    _published_for_reassessment(env, monkeypatch)
    monkeypatch.setattr(personal_models, "_external_llm_profiles", None)
    monkeypatch.setattr(openai_http_client, "_external_http_client", None)
    app = FastAPI()
    identity = SimpleNamespace(username="publisher", user_id="vendor-publisher")
    app.dependency_overrides[require_auth] = lambda: identity
    install_heart_model(app, tmp_path)
    body = {"request_id": str(uuid4()), "reason": "核查", "confirm_cost": True}
    url = f"/api/heart/evaluation/jobs/{env.job}/reassessment"
    with TestClient(app) as client:
        assert client.post(url, json={**body, "passed": True}).status_code == 422
        assert client.post(url, json={**body, "confirm_cost": False}).status_code == 409
        first = client.post(url, json=body)
        assert first.status_code == 200
        assert client.post(url, json=body).json()["id"] == first.json()["id"]
        identity.user_id = "rebound-vendor"
        assert client.post(url, json=body).status_code == 404



def _capability_message(dispatch):
    import json
    from integrations.deeptutor import model_capabilities as checks
    capability = dispatch["capability"]
    challenge = "HEART-" + dispatch["request_id"][:8]
    if capability == "chat": return SimpleNamespace(content=challenge)
    if capability == "vision": return SimpleNamespace(content=",".join(checks._vision_image(dispatch["request_id"])[1]))
    if capability == "tools": return SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(
        name="heart_capability_probe", arguments=json.dumps({"nonce": challenge})))])
    judgments = [{"assessable": True, "knowledge_point_id": sample["targets"][0]["id"], "passed": index == 0,
        "feedback": "与给定资料核对的样例结论", "answer_excerpt": sample["answer"],
        "citations": [{"source_id": "sample-source", "quote": sample["sources"][0]["text"]}]}
        for index, sample in enumerate(checks.assessment_samples())]
    return SimpleNamespace(content=json.dumps({"judgments": judgments}, ensure_ascii=False))


def test_chat_check_does_not_unlock_scoring_and_assessment_check_is_required(store, monkeypatch):
    import asyncio
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks, assessment_jobs as jobs
    store.save("cap-required", "https://public.example/v1", "model", "private-cap-key")
    version = store.read("cap-required")["credential_version"]
    job = jobs.enqueue("cap-required", "vendor-cap", "answer", {"answer": "A"}, "rule")
    assert jobs.status("cap-required", job)["status"] == "paused"
    assert jobs.status("cap-required", job)["last_error"] == "assessment_unverified"
    async def invoke(dispatch): return _capability_message(dispatch)
    monkeypatch.setattr(checks, "invoke", invoke)
    def run(capability):
        return asyncio.run(checks.run_check("cap-required", "vendor-cap", str(uuid4()), capability, version, confirm_cost=True))
    assert run("chat")["status"] == "passed"
    assert jobs.claim("cap-required") is None
    assert run("assessment")["status"] == "passed"
    assert jobs.status("cap-required", job)["status"] == "queued"
    assert jobs.claim("cap-required")["id"] == job
    assert not checks.assessment_ready("cap-required", "other-vendor", version)
    payload = checks.read_checks("cap-required", "vendor-cap")
    assert payload["capabilities"]["tools"]["status"] == "untested"
    assert "private-cap-key" not in str(payload)


@pytest.mark.parametrize("capability", ["chat", "assessment", "tools", "vision"])
def test_capability_probe_samples_validate_each_capability_independently(store, monkeypatch, capability):
    import asyncio
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks
    owner = "cap-" + capability
    store.save(owner, "https://public.example/v1", "model", "key")
    version = store.read(owner)["credential_version"]
    calls = []
    async def invoke(dispatch):
        calls.append(dispatch["capability"])
        return _capability_message(dispatch)
    monkeypatch.setattr(checks, "invoke", invoke)
    request_id = str(uuid4())
    first = asyncio.run(checks.run_check(owner, "vendor-cap", request_id, capability, version, confirm_cost=True))
    second = asyncio.run(checks.run_check(owner, "vendor-cap", request_id, capability, version, confirm_cost=True))
    assert first["status"] == second["status"] == "passed" and calls == [capability]


def test_assessment_probe_rejects_all_pass_and_preserves_chat_configuration(store, monkeypatch):
    import asyncio, json
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks, assessment_jobs as jobs
    store.save("cap-invalid", "https://public.example/v1", "model", "private-key")
    version = store.read("cap-invalid")["credential_version"]
    job = jobs.enqueue("cap-invalid", "vendor-cap", "answer", {"answer": "A"}, "rule")
    async def invoke(dispatch):
        message = _capability_message(dispatch)
        value = json.loads(message.content)
        value["judgments"][1]["passed"] = True
        return SimpleNamespace(content=json.dumps(value))
    monkeypatch.setattr(checks, "invoke", invoke)
    result = asyncio.run(checks.run_check("cap-invalid", "vendor-cap", str(uuid4()), "assessment", version, confirm_cost=True))
    assert result["status"] == "failed" and result["error_code"] == "response_invalid"
    assert jobs.status("cap-invalid", job)["status"] == "paused"
    assert store.runtime_config("cap-invalid")["api_key"] == "private-key"


def test_configuration_change_invalidates_checks_and_late_success_cannot_resume(store):
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks, assessment_jobs as jobs
    store.save("cap-version", "https://public.example/v1", "old", "old-key")
    old = store.read("cap-version")["credential_version"]
    dispatch, _ = checks.begin_check("cap-version", "vendor-cap", str(uuid4()), "assessment", old, confirm_cost=True)
    job = jobs.enqueue("cap-version", "vendor-cap", "answer", {"answer": "A"}, "rule")
    store.save("cap-version", "https://public.example/v1", "new", "new-key")
    assert checks.finish_check(dispatch, "passed") is False
    assert jobs.status("cap-version", job)["status"] == "paused"
    assert checks.read_checks("cap-version", "vendor-cap")["capabilities"]["assessment"]["status"] == "untested"
    with pytest.raises(ValueError, match="configuration_changed"):
        checks.begin_check("cap-version", "vendor-cap", str(uuid4()), "chat", old, confirm_cost=True)


def test_probe_unknown_is_not_retried_and_raw_provider_message_is_not_stored(store, monkeypatch):
    import asyncio
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks
    store.save("cap-timeout", "https://public.example/v1", "model", "private-key")
    version = store.read("cap-timeout")["credential_version"]
    calls = []
    async def invoke(dispatch):
        calls.append(1)
        raise TimeoutError("provider echoed private-key and private URL")
    monkeypatch.setattr(checks, "invoke", invoke)
    request_id = str(uuid4())
    for _ in range(2):
        result = asyncio.run(checks.run_check("cap-timeout", "vendor-cap", request_id, "chat", version, confirm_cost=True))
        assert result["status"] == "unknown"
        assert "private-key" not in str(result)
    assert calls == [1]
    assert "private-key" not in str(checks.read_checks("cap-timeout", "vendor-cap"))
    with pytest.raises(ValueError):
        checks.begin_check("cap-timeout", "vendor-cap", str(uuid4()), "chat", version, confirm_cost=False)


def test_probe_start_cancels_unsent_lease_and_expiry_is_unknown(store):
    from uuid import uuid4
    from datetime import timedelta
    from database.models import StudentModelCheck
    from integrations.deeptutor import model_capabilities as checks, assessment_jobs as jobs
    _save_verified(store, "cap-lease", "https://public.example/v1", "model", "key")
    version = store.read("cap-lease")["credential_version"]
    job = jobs.enqueue("cap-lease", "vendor-cap-lease", "answer", {"answer": "A"}, "rule")
    claim = jobs.claim("cap-lease")
    dispatch, _ = checks.begin_check("cap-lease", "vendor-cap-lease", str(uuid4()), "assessment", version, confirm_cost=True)
    assert jobs.begin_send("cap-lease", job, claim["lease_token"]) is None
    with store.session_scope(immediate=True) as session:
        session.get(StudentModelCheck, dispatch["check_id"]).lease_until = jobs._now() - timedelta(seconds=1)
    assert checks.read_checks("cap-lease", "vendor-cap-lease")["capabilities"]["assessment"]["status"] == "unknown"
    assert checks.finish_check(dispatch, "passed") is False


def test_runtime_authentication_rejection_pauses_current_and_future_scoring(store, monkeypatch):
    import asyncio
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks
    jobs, worker, job = _queue_scoring(store, monkeypatch, "cap-runtime")
    second = jobs.enqueue("cap-runtime", "vendor-cap-runtime", "second-answer", _scoring_input(), worker.RULE_VERSION)
    class AuthenticationFailure(Exception):
        status_code = 401
    calls = []
    async def judge(*args):
        calls.append(1); raise AuthenticationFailure("do not reveal private-key")
    monkeypatch.setattr(worker, "judge", judge)
    asyncio.run(worker.run_one("cap-runtime"))
    assert jobs.status("cap-runtime", job)["status"] == jobs.status("cap-runtime", second)["status"] == "paused"
    assert jobs.status("cap-runtime", job)["last_error"] == "authentication_failed"
    assert not asyncio.run(worker.run_one("cap-runtime")) and len(calls) == 1
    assert store.runtime_config("cap-runtime") is not None
    version = store.read("cap-runtime")["credential_version"]
    async def invoke(dispatch): return _capability_message(dispatch)
    monkeypatch.setattr(checks, "invoke", invoke)
    assert asyncio.run(checks.run_check("cap-runtime", "vendor-cap-runtime", str(uuid4()), "assessment", version, confirm_cost=True))["status"] == "passed"
    assert jobs.status("cap-runtime", job)["status"] == "queued"


def test_check_api_rejects_stale_versions_without_calling_model(store, monkeypatch, tmp_path):
    import asyncio
    from uuid import uuid4
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from deeptutor.api.routers.auth import require_auth
    from deeptutor.multi_user import personal_models
    from deeptutor.services.llm import openai_http_client
    from integrations.deeptutor.heart_model_api import install_heart_model
    from integrations.deeptutor import model_capabilities as checks
    monkeypatch.setattr(personal_models, "_external_llm_profiles", None)
    monkeypatch.setattr(openai_http_client, "_external_http_client", None)
    store.save("check-api", "https://public.example/v1", "model", "key")
    version = store.read("check-api")["credential_version"]
    calls = []
    async def invoke(dispatch): calls.append(1); return _capability_message(dispatch)
    monkeypatch.setattr(checks, "invoke", invoke)
    app = FastAPI(); app.dependency_overrides[require_auth] = lambda: SimpleNamespace(username="check-api", user_id="vendor-check-api")
    install_heart_model(app, tmp_path)
    body = {"request_id": str(uuid4()), "credential_version": version, "capability": "assessment", "confirm_cost": True}
    with TestClient(app) as client:
        assert client.post("/api/heart/model/checks", json={**body, "status": "passed"}).status_code == 422
        assert client.post("/api/heart/model/checks", json={**body, "confirm_cost": "true"}).status_code == 422
        assert client.post("/api/heart/model/checks", json={**body, "confirm_cost": False}).status_code == 409
        assert client.post("/api/heart/model/checks", json={**body, "credential_version": "0"*64}).status_code == 409
        assert calls == []
        assert client.post("/api/heart/model/checks", json=body).json()["status"] == "passed"
        assert client.post("/api/heart/model/checks", json=body).json()["status"] == "passed" and calls == [1]
        assert client.get("/api/heart/model/checks").headers["cache-control"] == "no-store"


def test_vision_sample_is_a_real_variable_png_and_wrong_color_order_fails(store):
    import base64, struct
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks
    request_id = str(uuid4())
    uri, colors = checks._vision_image(request_id)
    png = base64.b64decode(uri.split(",", 1)[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack("!II", png[16:24]) == (80, 80)
    assert len(set(colors)) == 4
    dispatch = {"capability": "vision", "request_id": request_id}
    assert checks.validate_response(dispatch, SimpleNamespace(content=",".join(colors)))
    assert not checks.validate_response(dispatch, SimpleNamespace(content=",".join(reversed(colors))))



@pytest.mark.parametrize("capability", ["chat", "assessment", "tools", "vision"])
def test_probe_sdk_request_is_single_and_uses_restricted_client(store, monkeypatch, capability):
    import asyncio
    from uuid import uuid4
    import openai
    from integrations.deeptutor import model_capabilities as checks, model_http
    dispatch = {"config": {"api_key": "test-private-key", "base_url": "https://public.example/v1", "model": "test-model"},
                "capability": capability, "request_id": str(uuid4())}
    requests, options = [], []
    restricted = object()
    monkeypatch.setattr(model_http, "build_student_http_client", lambda url: restricted)
    class FakeOpenAI:
        def __init__(self, **kwargs):
            options.append(kwargs)
            async def create(**payload):
                requests.append(payload)
                return SimpleNamespace(choices=[SimpleNamespace(message=_capability_message(dispatch))])
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(openai, "AsyncOpenAI", FakeOpenAI)
    assert checks.validate_response(dispatch, asyncio.run(checks.invoke(dispatch)))
    assert len(requests) == 1 and options[0]["max_retries"] == 0
    assert options[0]["http_client"] is restricted
    if capability == "tools":
        assert requests[0]["tool_choice"]["function"]["name"] == "heart_capability_probe"
    if capability == "vision":
        assert requests[0]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_concurrent_same_probe_request_invokes_provider_once(store, monkeypatch):
    import asyncio
    from uuid import uuid4
    from integrations.deeptutor import model_capabilities as checks
    store.save("cap-concurrent", "https://public.example/v1", "model", "key")
    version = store.read("cap-concurrent")["credential_version"]
    calls = []
    async def invoke(dispatch):
        calls.append(1); await asyncio.sleep(0.02); return _capability_message(dispatch)
    monkeypatch.setattr(checks, "invoke", invoke)
    request_id = str(uuid4())
    async def run():
        return await asyncio.gather(*[checks.run_check("cap-concurrent", "vendor-cap", request_id, "chat", version, confirm_cost=True) for _ in range(2)])
    results = asyncio.run(run())
    assert calls == [1] and any(item["status"] == "passed" for item in results)
    assert checks.read_checks("cap-concurrent", "vendor-cap")["capabilities"]["chat"]["status"] == "passed"



def test_native_guard_uses_current_verification_but_saved_publication_survives_config_change(publication_env, monkeypatch, tmp_path):
    import asyncio
    from fastapi import FastAPI
    from deeptutor.learning import service
    from deeptutor.multi_user import personal_models
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.services.llm import openai_http_client
    from integrations.deeptutor.heart_model_api import install_heart_model
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    monkeypatch.setattr(service, "_external_assessment_guard", None)
    monkeypatch.setattr(personal_models, "_external_llm_profiles", None)
    monkeypatch.setattr(openai_http_client, "_external_http_client", None)
    install_heart_model(FastAPI(), tmp_path)
    token = set_current_user(SimpleNamespace(username="publisher", id="vendor-publisher", is_admin=False))
    try:
        service.require_assessment_capability()
        env.store.save("publisher", "https://public.example/v1", "unverified-model", "new-key")
        with pytest.raises(service.MasteryInteractionError):
            service.require_assessment_capability()
    finally:
        reset_current_user(token)
    assert asyncio.run(publish_one("publisher", env.job))
    assert env.jobs.status("publisher", env.job)["publication_status"] == "published"



def test_chapter_progress_requires_current_catalog_and_vendor_identity(publication_env, monkeypatch):
    import asyncio
    from integrations.deeptutor import learning_projection
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    catalog = {"kc-1-1": {"id": "kc-1-1", "name": "自变量", "chapter_id": 1, "section_id": 1}}
    monkeypatch.setattr(learning_projection, "confirmed_catalog", lambda: (catalog, "registry-test"))
    def point(vendor="vendor-publisher"):
        return learning_projection.chapter_progress("publisher", vendor, 1)["points"][0]
    assert point()["snapshot"] is None and point()["sync_pending"]
    assert not point("rebound-id")["sync_pending"]
    assert asyncio.run(publish_one("publisher", env.job))
    assert point()["snapshot"]["assessed_mastered"] is False
    assert point()["snapshot"]["next_review_at"] is None
    assert not point()["sync_pending"]
    assert point("rebound-id")["snapshot"] is None
    assert learning_projection.chapter_progress("publisher", "vendor-publisher", 2)["points"] == []
    monkeypatch.setattr(learning_projection, "confirmed_catalog", lambda: (catalog, "next-version"))
    assert point()["snapshot"] is None



def test_practice_review_outbox_recovers_after_pg_failure_and_replay(publication_env, monkeypatch):
    import asyncio
    import json
    from sqlalchemy import select, func
    from database.models import EvidenceRow, LearningEventRow
    from database.repository import Repository
    from deeptutor.learning.assessment import AssessmentRecord, record_assessment
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.services.practice import storage
    from integrations.deeptutor import practice_sync
    env = publication_env
    monkeypatch.setattr(practice_sync, "confirmed_catalog", lambda: ({"kc-1-1": {}}, "registry-test"))
    monkeypatch.setattr(storage, "_review_export", practice_sync.capture)
    outcome = asyncio.run(record_assessment(AssessmentRecord(session_id="session-score", turn_id="practice-seed",
        question_id="q-practice", question="选出正确答案", question_type="single_choice", correct_answer="B",
        options={"A": "错误", "B": "正确"}, source="mastery_path", result="incorrect",
        mastery_path_id="path-score", knowledge_point_id="kc-1-1")))
    repo = storage.PracticeStore(env.notebook.db_path)
    token = set_current_user(SimpleNamespace(username="publisher", id="vendor-publisher", is_admin=False))
    try:
        version = repo.state(outcome.entry_id)["version"]
        reviewed = repo.review(outcome.entry_id, "practice-sync-1", version, "good", "B")
        assert reviewed["learning_sync"] == "pending" and reviewed["correct"] is True
        with repo.connect() as conn:
            event = dict(conn.execute("SELECT * FROM practice_review_outbox").fetchone())
        original = Repository.add_event_evidence
        def fail(*args, **kwargs): raise RuntimeError("temporary PG failure")
        monkeypatch.setattr(Repository, "add_event_evidence", fail)
        with pytest.raises(RuntimeError):
            practice_sync.drain_store(repo, "publisher", "vendor-publisher", "")
        assert repo.review(outcome.entry_id, "practice-sync-1", version, "good", "B") == reviewed
        monkeypatch.setattr(Repository, "add_event_evidence", original)
        practice_sync.drain_store(repo, "publisher", "wrong-vendor", "")
        assert repo.review(outcome.entry_id, "practice-sync-1", version, "good", "B")["learning_sync"] == "pending"
        practice_sync.drain_store(repo, "publisher", "vendor-publisher", "")
        assert repo.review(outcome.entry_id, "practice-sync-1", version, "good", "B")["learning_sync"] == "synced"
        assert practice_sync.sync(event["event_id"], json.loads(event["payload_json"])) == "synced"
        with env.store.session_scope() as session:
            assert session.scalar(select(func.count()).select_from(EvidenceRow)) == 1
            saved = session.scalar(select(LearningEventRow)).payload
            assert saved["review"]["correct"] is True and "mastered" not in saved["review"]
        from integrations.deeptutor import learning_projection
        catalog = {"kc-1-1": {"id": "kc-1-1", "name": "自变量", "chapter_id": 1, "section_id": 1}}
        monkeypatch.setattr(learning_projection, "confirmed_catalog", lambda: (catalog, "registry-test"))
        chapter = learning_projection.chapter_progress("publisher", "vendor-publisher", 1)["points"][0]
        assert chapter["practice_review"]["correct"] is True and chapter["snapshot"] is None
        assert learning_projection.chapter_progress("publisher", "wrong-vendor", 1)["points"][0]["practice_review"] is None
        assert env.learning.load("path-score").qualitative_mastery == {}
        with repo.connect() as conn:
            conn.execute("UPDATE notebook_entries SET correct_answer = 'A' WHERE id = ?", (outcome.entry_id,))
        edited = repo.review(outcome.entry_id, "practice-sync-2", repo.state(outcome.entry_id)["version"], "good", "A")
        assert "learning_sync" not in edited
    finally:
        reset_current_user(token)



@pytest.mark.parametrize("send_method", ["chat_with_retry", "chat_stream_with_retry"])
def test_student_image_requests_require_current_owner_bound_vision_check(store, monkeypatch, tmp_path, send_method):
    import asyncio
    from uuid import uuid4
    from fastapi import FastAPI
    from deeptutor.learning import service
    from deeptutor.multi_user import personal_models
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.services.llm import multimodal as mm, openai_http_client
    from deeptutor.services.llm.provider_core.base import LLMProvider, LLMResponse
    from integrations.deeptutor import model_capabilities as checks
    from integrations.deeptutor.heart_model_api import install_heart_model
    for module, name in [(mm, "_external_image_guard"), (service, "_external_assessment_guard"),
                         (personal_models, "_external_llm_profiles"), (openai_http_client, "_external_http_client")]:
        monkeypatch.setattr(module, name, None)
    install_heart_model(FastAPI(), tmp_path)
    owner, vendor = "vision-input-owner", "vendor-vision-input"
    version = store.save(owner, "https://public.example/v1", "image-model", "image-key")
    image = SimpleNamespace(type="image", base64="aW1hZ2U=", mime_type="image/png")
    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}}]}]
    class RejectingProvider(LLMProvider):
        def __init__(self):
            super().__init__()
            self.calls = []
        def get_default_model(self):
            return "image-model"
        async def chat(self, messages, **kwargs):
            self.calls.append(messages)
            return LLMResponse(content="unsupported image input", finish_reason="error")
    provider = RejectingProvider()
    token = set_current_user(SimpleNamespace(username=owner, id=vendor, is_admin=False))
    try:
        # 普通文字仍可使用；未验证图片不能发出请求。
        assert mm.prepare_multimodal_messages([{"role": "user", "content": "hello"}], []).messages
        with pytest.raises(ValueError, match="图片能力"):
            mm.prepare_multimodal_messages([{"role": "user", "content": "describe"}], [image], model="image-model")
        with pytest.raises(ValueError, match="图片能力"):
            asyncio.run(getattr(provider, send_method)(messages=messages, retry_delays=()))
        assert provider.calls == []
        dispatch, _ = checks.begin_check(owner, "other-vendor", str(uuid4()), "vision", version, confirm_cost=True)
        assert checks.finish_check(dispatch, "passed")
        with pytest.raises(ValueError):
            mm.require_image_capability("image-model")
        dispatch, _ = checks.begin_check(owner, vendor, str(uuid4()), "vision", version, confirm_cost=True)
        assert checks.finish_check(dispatch, "passed")
        prepared = mm.prepare_multimodal_messages([{"role": "user", "content": "describe"}], [image], model="image-model")
        assert mm.has_image_parts(prepared.messages)
        assert not mm.should_degrade_to_text("unknown-provider", "image-model", prepared.messages)
        asyncio.run(getattr(provider, send_method)(messages=messages, retry_delays=(), allow_image_fallback=True))
        assert len(provider.calls) == 1 and mm.has_image_parts(provider.calls[0])
        with pytest.raises(ValueError, match="完整读取"):
            mm.prepare_multimodal_messages([{"role": "user", "content": "describe"}], [image, SimpleNamespace(type="image")], model="image-model")
        monkeypatch.setattr(mm, "_resolve_local_attachment_url", lambda _: None)
        with pytest.raises(ValueError, match="完整读取"):
            mm.prepare_multimodal_messages([{"role": "user", "content": "describe"}], [SimpleNamespace(type="image", url="/files/attachments/s/a/expired.png")], model="image-model")
        with pytest.raises(ValueError, match="对应的提问"):
            mm.prepare_multimodal_messages([], [image], model="image-model")
        with pytest.raises(ValueError):
            mm.require_image_capability("other-model")
        store.save(owner, "https://public.example/v1", "image-model", "changed-key")
        with pytest.raises(ValueError):
            mm.require_image_capability("image-model")
    finally:
        reset_current_user(token)
    admin = set_current_user(SimpleNamespace(username="admin", id="admin", is_admin=True))
    try:
        assert mm.require_image_capability("admin-model") is False
    finally:
        reset_current_user(admin)



@pytest.mark.parametrize("change,expected", [
    ({}, "assisted"), ({"message_id": 19}, "not_verified"),
    ({"message_id": "21"}, "not_verified"), ({"catalog_version": "new-catalog"}, "not_verified"),
    ({"session_id": "other-session"}, "not_verified"), ({"turn_id": "reference-turn"}, "not_verified"),
    ({"knowledge_point_id": "other-point"}, "not_verified"),
])
@pytest.mark.parametrize("with_quiz", [False, True])
def test_chat_reference_order_is_scoped_without_requiring_a_quiz(tmp_path, monkeypatch, change, expected, with_quiz):
    from integrations.deeptutor import assessment_intake as intake
    from deeptutor.learning import storage
    from deeptutor.learning.models import LearningProgress, LearningModule, KnowledgePoint, KnowledgeType, PendingQuestion
    from deeptutor.learning.service import LearningService
    from concurrent.futures import ThreadPoolExecutor
    learning = storage.LearningStore(tmp_path / "reference-order")
    learning.save(LearningProgress(book_id="reference-path", modules=[LearningModule(id="m", name="教材节", order=0,
        knowledge_points=[KnowledgePoint(id="kc-1-1", name="自变量", type=KnowledgeType.CONCEPT, module_id="m")])]))
    monkeypatch.setattr(storage, "LearningStore", lambda: learning)
    snapshot = {"mastery_path_id": "reference-path", "session_id": "reference-session", "turn_id": "reference-turn",
        "catalog_version": "catalog-1", "sources": [{"id": "textbook-source", "version": "book-v1", "text": "quote"}],
        "targets": [{"id": "kc-1-1", "source_ids": ["textbook-source"]}]}
    context = SimpleNamespace(metadata={"persisted_assistant_message_id": 20})
    events = [{"type": "sources", "metadata": {"sources": [{"source_id": "textbook-source"}]}}]
    # 并发完成通知也只产生一条暴露事件，重开 store 后记录仍在。
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: intake.record_displayed_references(snapshot, context, events), range(2)))
    learning = type(learning)(tmp_path / "reference-order")
    references = learning.list_events("reference-path")
    assert sum(e.event_type == "chat.reference_provided" for e in references) == 1
    if with_quiz:
        service = LearningService(learning)
        service.register_question("reference-path", PendingQuestion(question_id="question-after-chat", knowledge_point_id="kc-1-1",
            prompt="请解释自变量", expected_answer="answer"), session_id="reference-session", turn_id="question-turn")
        service.record_question_answer("reference-path", "my answer", interaction_id="question-after-chat",
            session_id="reference-session", turn_id="answer-turn")
    execution = SimpleNamespace(session_id=change.get("session_id", "reference-session"), turn_id=change.get("turn_id", "answer-turn"))
    kp = change.get("knowledge_point_id", "kc-1-1")
    result = intake.assistance_for_turn(learning, "reference-path", execution, "my answer", {kp: {}},
        message_id=change.get("message_id", 21), catalog_version=change.get("catalog_version", "catalog-1"))[kp]
    assert result["status"] == expected and result["coverage"] == "partial"
    if expected == "assisted":
        assert result["events"][0]["assistant_message_id"] == 20
    assert "quote" not in str(references[-1].payload)


def test_chat_internal_sources_and_missing_server_message_id_do_not_mark_exposure(tmp_path, monkeypatch):
    from integrations.deeptutor import assessment_intake as intake
    from deeptutor.learning import storage
    from deeptutor.learning.models import LearningProgress
    learning = storage.LearningStore(tmp_path / "internal-sources")
    learning.save(LearningProgress(book_id="reference-path", modules=[]))
    monkeypatch.setattr(storage, "LearningStore", lambda: learning)
    snapshot = {"mastery_path_id": "reference-path", "session_id": "s", "turn_id": "t", "catalog_version": "v",
        "sources": [{"id": "verified", "version": "v"}], "targets": [{"id": "kc-1-1", "source_ids": ["verified"]}]}
    events = [{"type": "tool_result", "metadata": {"sources": [{"source_id": "verified"}]}}]
    intake.record_displayed_references(snapshot, SimpleNamespace(metadata={"persisted_assistant_message_id": 2}), events)
    events[0]["type"] = "sources"
    intake.record_displayed_references(snapshot, SimpleNamespace(metadata={}), events)
    events[0]["metadata"]["sources"][0]["source_id"] = "unverified"
    intake.record_displayed_references(snapshot, SimpleNamespace(metadata={"persisted_assistant_message_id": 2}), events)
    assert all(e.event_type != "chat.reference_provided" for e in learning.list_events("reference-path"))



@pytest.mark.parametrize("case", ["provided", "empty_reply", "missing_id", "other_turn", "other_session", "unconfirmed", "tool_failed", "admin"])
def test_explicit_teaching_without_sources_is_traced_only_after_completed_reply(tmp_path, monkeypatch, case):
    import asyncio
    from integrations.deeptutor import assessment_intake as intake
    from deeptutor.learning import storage
    from deeptutor.learning.service import LearningService
    from deeptutor.learning.models import LearningProgress, LearningModule, KnowledgePoint, KnowledgeType
    from deeptutor.capabilities.mastery import tools
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    learning = storage.LearningStore(tmp_path / "no-source-teaching")
    points = [KnowledgePoint(id=kp, name=kp, type=KnowledgeType.CONCEPT, module_id="m") for kp in ["kc-1-1", "unconfirmed"]]
    learning.save(LearningProgress(book_id="teaching-path", modules=[LearningModule(id="m", name="教材节", order=0, knowledge_points=points)]))
    monkeypatch.setattr(storage, "LearningStore", lambda: learning)
    monkeypatch.setattr(intake, "confirmed_catalog", lambda: ({"kc-1-1": {}}, "catalog-1"))
    monkeypatch.setattr(intake.jobs, "enqueue", lambda *args: pytest.fail("无教材依据时不应发起评分"))
    token = set_current_user(SimpleNamespace(username="teacher-trace", id="vendor-teacher-trace", is_admin=case == "admin"))
    try:
        kp = "unconfirmed" if case == "unconfirmed" else "missing-point" if case == "tool_failed" else "kc-1-1"
        result = asyncio.run(tools.MasteryNoteExplainedTool().execute(_mastery_path_id="teaching-path",
            _session_id="teaching-session", _turn_id="teaching-turn", knowledge_point_id=kp, summary="private teaching summary"))
        assert result.success == (case != "tool_failed")
        original = [e for e in learning.list_events("teaching-path") if e.event_type == "objective.explained"]
        if original:
            assert original[0].session_id == "teaching-session" and original[0].turn_id == "teaching-turn"
        execution = SimpleNamespace(session_id="other-session" if case == "other_session" else "teaching-session",
            turn_id="other-turn" if case == "other_turn" else "teaching-turn", payload={"content": "请讲解"})
        context = SimpleNamespace(metadata={"mastery_path_id": "teaching-path", "persisted_assistant_message_id": None if case == "missing_id" else 20,
            "persisted_assistant_has_content": case != "empty_reply"}, attachments=[], conversation_history=[])
        for _ in range(2):
            asyncio.run(intake.completed_turn(execution, context, [], 19))
        recorded = [e for e in learning.list_events("teaching-path") if e.event_type == "chat.teaching_provided"]
        assert len(recorded) == (1 if case == "provided" else 0)
        if case == "provided":
            assert recorded[0].payload["source_event_ids"] == [original[0].id]
            assert "private teaching summary" not in str(recorded[0].payload)
            later = SimpleNamespace(session_id="teaching-session", turn_id="later-answer")
            status = intake.assistance_for_turn(learning, "teaching-path", later, "answer", {"kc-1-1": {}}, message_id=21, catalog_version="catalog-1")
            assert status["kc-1-1"]["status"] == "assisted"
            assert status["kc-1-1"]["reason"] == "teaching_provided"
            assert status["kc-1-1"]["events"][0]["source_event_ids"] == [original[0].id]
            for mid, version in [(19, "catalog-1"), (21, "new-catalog")]:
                assert intake.assistance_for_turn(learning, "teaching-path", later, "answer", {"kc-1-1": {}}, message_id=mid, catalog_version=version)["kc-1-1"]["status"] == "not_verified"
    finally:
        reset_current_user(token)



def test_no_source_teaching_assistance_survives_vendor_and_h_publication(publication_env, monkeypatch):
    import asyncio
    import json
    from hashlib import sha256
    from sqlalchemy import select
    from database.models import AssessmentJobRow, LearningEventRow, EventEvidenceRow
    from integrations.deeptutor import assessment_intake as intake
    from integrations.deeptutor.assessment_publication import publish_one
    from deeptutor.capabilities.mastery import tools
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    env = publication_env
    dispatch = env.jobs.publication("publisher", env.job)
    snapshot = dispatch["input"]
    monkeypatch.setattr(intake, "confirmed_catalog", lambda: ({"kc-1-1": {}}, snapshot["catalog_version"]))
    token = set_current_user(SimpleNamespace(username="publisher", id="vendor-publisher", is_admin=False))
    try:
        result = asyncio.run(tools.MasteryNoteExplainedTool().execute(_mastery_path_id="path-score",
            _session_id=snapshot["session_id"], _turn_id="earlier-teaching", knowledge_point_id="kc-1-1", summary="解释了自变量"))
        assert result.success
        intake.record_completed_teaching(SimpleNamespace(session_id=snapshot["session_id"], turn_id="earlier-teaching"),
            SimpleNamespace(metadata={"mastery_path_id": "path-score", "persisted_assistant_message_id": 20, "persisted_assistant_has_content": True}))
        snapshot["assistance"] = intake.assistance_for_turn(env.learning, "path-score",
            SimpleNamespace(session_id=snapshot["session_id"], turn_id=snapshot["turn_id"]), snapshot["answer"], {"kc-1-1": {}},
            message_id=21, catalog_version=snapshot["catalog_version"])
    finally:
        reset_current_user(token)
    assert snapshot["assistance"]["kc-1-1"]["status"] == "assisted"
    # 给已完成的固定评分 fixture 装入这次真实追踪得到的辅助快照。
    with env.store.session_scope(immediate=True) as session:
        row = session.get(AssessmentJobRow, env.job)
        row.input = snapshot
        row.input_hash = sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    assert asyncio.run(publish_one("publisher", env.job))
    evidence = env.learning.load("path-score").learning_evidence[0]
    assert evidence.hints_used and evidence.visual_context["independent"] is False
    assert evidence.visual_context["assistance"]["reason"] == "teaching_provided"
    with env.store.session_scope() as session:
        receipt = session.scalar(select(LearningEventRow)).payload
        linked = session.scalar(select(EventEvidenceRow))
        assert receipt["assessment"]["visual_context"]["assistance_status"] == "assisted"
        assert not receipt["assessed_mastered"] and not linked.independent
    recent = env.jobs.recent_jobs("publisher", "vendor-publisher")["jobs"][0]
    assert recent["assistance_status"] == "assisted"



def test_model_fixture_fails_before_writing_if_engine_was_initialized_early(request, monkeypatch):
    credentials = request.getfixturevalue("store")
    previous = dict(os.environ)
    monkeypatch.setattr(credentials, "engine", SimpleNamespace(url=SimpleNamespace(database="forbidden-production-database")))
    monkeypatch.setattr(credentials, "ensure_table", lambda: pytest.fail("错误的库连接不得建表或写入"))
    nested = globals()["store"].__wrapped__()
    with pytest.raises(AssertionError, match="随机临时库"):
        next(nested)
    assert dict(os.environ) == previous



def test_memory_observation_publishes_atomically_with_evidence_and_never_regrades(publication_env, monkeypatch):
    import asyncio
    import json
    from hashlib import sha256
    from datetime import timedelta
    from sqlalchemy import select, func
    from database.models import Base, StudentMemorySetting, MemoryDocumentRow, AssessmentJobRow, EvidenceRow
    from integrations.deeptutor import student_memory
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    Base.metadata.create_all(env.store.engine, tables=[StudentMemorySetting.__table__, MemoryDocumentRow.__table__])
    with env.store.session_scope(immediate=True) as session:
        row = session.get(AssessmentJobRow, env.job)
        row.input = {**row.input, "memory_control": {"enabled": True, "revision": 0}}
        row.input_hash = sha256(json.dumps(row.input, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    original = student_memory.record_assessment_memory
    def failed_after_note(session, job, receipt, event_id):
        assert original(session, job, receipt, event_id)
        session.flush()
        raise RuntimeError("injected memory transaction failure")
    monkeypatch.setattr(student_memory, "record_assessment_memory", failed_after_note)
    assert not asyncio.run(publish_one("publisher", env.job))
    with env.store.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(MemoryDocumentRow)) == 0
        assert session.scalar(select(func.count()).select_from(EvidenceRow)) == 0
    monkeypatch.setattr(student_memory, "record_assessment_memory", original)
    with env.store.session_scope(immediate=True) as session:
        session.get(AssessmentJobRow, env.job).ready_at = env.jobs._now() - timedelta(seconds=1)
    async def forbidden(*args): pytest.fail("同步重试不能调用评分模型")
    monkeypatch.setattr(env.worker, "judge", forbidden)
    assert asyncio.run(publish_one("publisher", env.job))
    assert not asyncio.run(publish_one("publisher", env.job))
    with env.store.session_scope() as session:
        docs = session.scalars(select(MemoryDocumentRow)).all()
        assert len(docs) == 1 and docs[0].source_metadata["verification"] == "learning_inference"
        assert docs[0].source_metadata["job_id"] == env.job and docs[0].source_metadata["event_id"]
        assert session.scalar(select(func.count()).select_from(EvidenceRow)) == 1
    assert not env.learning.load("path-score").qualitative_mastery


def test_publication_after_source_deleted_keeps_evidence_without_recreating_chat(publication_env):
    import asyncio
    from integrations.deeptutor.assessment_publication import publish_one
    env = publication_env
    asyncio.run(env.notebook.delete_session("session-score"))
    assert asyncio.run(publish_one("publisher", env.job))
    assert not asyncio.run(publish_one("publisher", env.job))
    with env.notebook._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", ("session-score",)).fetchone()[0] == 0
        row = conn.execute("SELECT session_id, origin_ref FROM assessment_attempts").fetchone()
        assert row["session_id"] is None and row["origin_ref"] == "session-score"
        card = conn.execute("SELECT session_id, origin_ref FROM notebook_entries").fetchone()
        assert card["session_id"] is None and card["origin_ref"] == "session-score"
    assert len(env.learning.load("path-score").learning_evidence) == 1
    assert env.jobs.status("publisher", env.job)["publication_status"] == "published"
