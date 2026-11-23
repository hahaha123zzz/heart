"""学生记忆 H 唯一来源：随机临时 PG，禁止真实模型与正式库。"""
import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.fixture(scope="module")
def memory(tmp_path_factory):
    from tests.pg_support import temp_databases
    previous = dict(os.environ)
    try:
        with temp_databases("heart_student_memory") as env:
            os.environ.update(env)
            os.environ["MEM0_ENABLED"] = "0"
            os.environ["DEEPTUTOR_HOME"] = str(tmp_path_factory.mktemp("vendor-memory-home"))
            from integrations.deeptutor import student_memory
            from sqlalchemy.engine import make_url
            expected = {make_url(env[k]).database for k in ("DATABASE_URL", "COURSE_DATABASE_URL")}
            assert student_memory.engine.url.database in expected, "记忆测试禁止使用非本次临时库连接"
            student_memory.Base.metadata.create_all(student_memory.engine)
            try:
                yield student_memory
            finally:
                student_memory.engine.dispose()
    finally:
        os.environ.clear()
        os.environ.update(previous)


@pytest.fixture
def ui(memory, monkeypatch):
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from deeptutor.api.routers.auth import require_auth
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.services.memory import store, paths
    from deeptutor.runtime import turn_engine
    from deeptutor.services.session import context_builder
    from integrations.deeptutor.heart_memory_api import install_heart_memory
    actor = {"username": "memory-" + uuid4().hex[:10], "user_id": "vendor-" + uuid4().hex[:10]}
    user = SimpleNamespace(username=actor["username"], id=actor["user_id"], is_admin=False)
    token = set_current_user(user)
    monkeypatch.setattr(store, "_external_memory_store", None)
    monkeypatch.setattr(paths, "_external_root_guard", None)
    monkeypatch.setattr(turn_engine, "_external_context_preparer", None)
    monkeypatch.setattr(context_builder, "_external_history_preparer", None)
    monkeypatch.setattr(context_builder, "_external_summary_wrapper", None)
    app = FastAPI()
    async def auth():
        set_current_user(SimpleNamespace(username=actor["username"], id=actor["user_id"], is_admin=False))
        return SimpleNamespace(**actor)
    app.dependency_overrides[require_auth] = auth
    install_heart_memory(app)
    monkeypatch.setattr(memory, "current_catalog_version", lambda: "catalog-test")
    @app.get("/native-memory-path", dependencies=[Depends(require_auth)])
    def native_path():
        return {"path": str(paths.memory_root())}
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, actor=actor, user=user, memory=memory)
    finally:
        reset_current_user(token)


def test_preferences_use_pg_stable_ids_and_no_implicit_chat_writes(ui):
    from deeptutor.services.memory import get_memory_store
    client = ui.client
    assert client.get("/api/heart/memory").json()["preferences"] == []
    first = client.post("/api/heart/memory/preference", json={"text": "先给结论，再举例"}).json()["preferences"][0]
    second = client.post("/api/heart/memory/preference", json={"text": "  先给结论，再举例  "}).json()["preferences"][0]
    assert first["id"] == second["id"] and first["source"] == "explicit_user"
    assert "先给结论" in get_memory_store().read_l3_concat()
    report = asyncio.run(get_memory_store().write_preference(op="add", text="模型推断", trace_id="turn"))
    assert not report.accepted
    assert len(client.get("/api/heart/memory").json()["preferences"]) == 1
    assert client.get("/api/heart/memory").headers["cache-control"] == "no-store"


def test_disable_stops_generation_reads_but_allows_manage_and_manual_preferences(ui):
    from deeptutor.services.memory import get_memory_store
    client = ui.client
    client.post("/api/heart/memory/preference", json={"text": "多举例"})
    before = client.get("/api/heart/memory/settings").json()
    assert before == {"enabled": True, "revision": 0}
    assert client.put("/api/heart/memory/settings", json={"enabled": "false"}).status_code == 422
    assert client.put("/api/heart/memory/settings", json={"enabled": False}).json() == {"enabled": False, "revision": 1}
    assert get_memory_store().read_l3_concat() == ""
    assert client.get("/api/heart/memory").json()["preferences"]
    assert client.post("/api/heart/memory/preference", json={"text": "讲慢一些"}).status_code == 200
    assert get_memory_store().read_l3_concat() == ""
    assert client.put("/api/heart/memory/settings", json={"enabled": False}).json()["revision"] == 1
    assert client.put("/api/heart/memory/settings", json={"enabled": True}).json()["revision"] == 2
    assert "讲慢一些" in get_memory_store().read_l3_concat()


def test_delete_is_owner_bound_and_cannot_be_resurrected_by_old_index_rebuild(ui):
    from database.memory_index import MemoryIndexRepository
    from deeptutor.services.memory import get_memory_store
    client, actor = ui.client, ui.actor
    card = client.post("/api/heart/memory/preference", json={"text": "删除不复活"}).json()["preferences"][0]
    original = dict(actor)
    actor.update(username="different-" + uuid4().hex[:8], user_id="another-vendor")
    assert client.get("/api/heart/memory").json()["preferences"] == []
    assert client.delete(f"/api/heart/memory/preference/{card['id']}").status_code == 404
    actor.update(original)
    repo = MemoryIndexRepository()
    repo.sync_memory_index(actor["username"])
    assert client.get("/api/heart/memory").json()["preferences"][0]["id"] == card["id"]
    assert client.delete(f"/api/heart/memory/preference/{card['id']}").status_code == 200
    repo.sync_memory_index(actor["username"])
    assert client.get("/api/heart/memory").json()["preferences"] == []
    assert "删除不复活" not in get_memory_store().read_l3_concat()
    assert client.delete(f"/api/heart/memory/preference/{card['id']}").status_code == 404
    added = client.post("/api/heart/memory/preference", json={"text": "删除不复活"}).json()["preferences"][0]
    assert added["id"] != card["id"]


def test_vendor_files_are_blocked_and_pg_failure_does_not_fall_back(ui, monkeypatch):
    from deeptutor.services.memory import get_memory_store, paths
    from deeptutor.services.memory.store import MemoryStore
    assert ui.client.get("/native-memory-path").status_code == 403
    with pytest.raises(paths.MemoryAccessDisabledError):
        MemoryStore().read_raw("L3", "preferences")
    def unavailable(*args, **kwargs):
        raise RuntimeError("private connection data must not leak")
    monkeypatch.setattr(ui.memory, "overview", unavailable)
    assert get_memory_store().read_l3_concat() == ""
    response = ui.client.get("/api/heart/memory")
    assert response.status_code == 503 and "private connection" not in response.text


def test_reused_username_with_different_vendor_identity_fails_closed(ui):
    ui.client.post("/api/heart/memory/preference", json={"text": "旧身份偏好"})
    ui.actor["user_id"] = "changed-vendor"
    assert ui.client.get("/api/heart/memory").status_code == 409
    assert ui.client.post("/api/heart/memory/preference", json={"text": "不能覆盖绑定"}).status_code == 409


def test_manual_memory_does_not_create_scores_or_mastery(ui):
    from sqlalchemy import select, func
    from database.models import EvidenceRow, LearningEventRow, KnowledgeStateRow
    ui.client.post("/api/heart/memory/preference", json={"text": "我已经掌握全部知识点"})
    with ui.memory.session_scope() as session:
        for model in [EvidenceRow, LearningEventRow, KnowledgeStateRow]:
            assert session.scalar(select(func.count()).select_from(model).where(model.student_id == ui.user.username)) == 0
    assert ui.client.post("/api/heart/memory/preference", json={"text": "  "}).status_code == 400



def test_search_uses_only_current_owner_and_treats_wildcards_as_text(ui):
    ui.client.post("/api/heart/memory/preference", json={"text": "多举例"})
    ui.client.post("/api/heart/memory/preference", json={"text": "先给结论"})
    result = ui.client.get("/api/heart/memory", params={"q": "举例"}).json()
    assert [c["text"] for c in result["preferences"]] == ["多举例"]
    assert ui.client.get("/api/heart/memory", params={"q": "%"}).json()["preferences"] == []
    assert ui.client.get("/api/heart/memory", params={"q": "x" * 101}).status_code == 422



def _job(ui, token=None):
    owner, vendor = ui.user.username, ui.user.id
    ui.memory.add_preference(owner, vendor, "测试偏好")
    token = token if token is not None else ui.memory.settings(owner, vendor)
    job = SimpleNamespace(id=str(uuid4()), student_id=owner, vendor_user_id=vendor,
        input={"memory_control": token, "targets": [{"id": "kc-1-1", "name": "自变量"}], "catalog_version": "catalog-test"},
        result={"judgment": {"passed": False}})
    receipt = {"student_id": owner, "vendor_user_id": vendor, "knowledge_point_id": "kc-1-1", "job_id": job.id,
        "assessment": {"visual_context": {"catalog_version": "catalog-test"}}}
    return job, receipt


def _record(ui, job, receipt):
    from database.models import LearningEventRow
    with ui.memory.session_scope(immediate=True) as session:
        if session.get(LearningEventRow, job.id) is None:
            session.add(LearningEventRow(id=job.id, student_id=job.student_id, source_key="memory-test:" + job.id,
                knowledge_point="kc-1-1", event_type="vendor_assessment", status="synced", payload=receipt))
            session.flush()
        return ui.memory.record_assessment_memory(session, job, receipt, job.id)


@pytest.mark.parametrize("change", ["none", "off", "off_then_on", "delete"])
def test_automatic_record_respects_original_control_and_discards_late_work(ui, change):
    job, receipt = _job(ui)
    owner, vendor = ui.user.username, ui.user.id
    if change in {"off", "off_then_on"}:
        ui.memory.set_enabled(owner, vendor, False)
    if change == "off_then_on":
        ui.memory.set_enabled(owner, vendor, True)
    if change == "delete":
        card = ui.memory.overview(owner, vendor)["preferences"][0]
        ui.memory.delete_entry(owner, vendor, "preference", int(card["id"]))
    assert _record(ui, job, receipt) is (change == "none")
    profiles = ui.memory.overview(owner, vendor)["profile"]
    assert len(profiles) == (1 if change == "none" else 0)
    if profiles:
        assert profiles[0]["source"] == "learning_inference"
        assert "未确认" in profiles[0]["text"] and "不代表独立掌握" in profiles[0]["text"]
    assert not _record(ui, job, receipt)


def test_deleted_auto_record_is_not_revived_and_disabled_source_is_not_backscanned(ui):
    owner, vendor = ui.user.username, ui.user.id
    job, receipt = _job(ui)
    assert _record(ui, job, receipt)
    card = ui.memory.overview(owner, vendor)["profile"][0]
    ui.memory.delete_entry(owner, vendor, "profile", int(card["id"]))
    job.input["memory_control"] = ui.memory.settings(owner, vendor)
    assert not _record(ui, job, receipt)
    disabled, receipt = _job(ui, {"enabled": False, "revision": ui.memory.settings(owner, vendor)["revision"]})
    assert not _record(ui, disabled, receipt)
    assert ui.memory.overview(owner, vendor)["profile"] == []


def test_mem0_candidates_are_revalidated_against_pg_and_never_supply_their_own_body(ui, monkeypatch):
    from database.models import MemoryDocumentRow
    job, receipt = _job(ui)
    assert _record(ui, job, receipt)
    owner, vendor = ui.user.username, ui.user.id
    profile = ui.memory.overview(owner, vendor)["profile"][0]
    with ui.memory.session_scope(immediate=True) as session:
        row = session.get(MemoryDocumentRow, int(profile["id"]))
        row.mem0_id = "current-memory-id"; row.mem0_synced_hash = row.content_hash
    class Candidates:
        def search(self, student_id, query, limit=20):
            assert student_id == owner
            return [{"card_id": int(profile["id"]), "memory_id": "current-memory-id", "content": "旧缓存伪造正文"},
                    {"card_id": 999999999, "memory_id": "foreign"}, "malformed"]
    monkeypatch.setattr(ui.memory, "get_mem0", lambda: Candidates())
    result = ui.memory.generation_cards(owner, vendor, "自变量")
    assert [card["text"] for card in result["profile"]] == [profile["text"]]
    assert "旧缓存伪造正文" not in str(result)
    ui.memory.delete_entry(owner, vendor, "profile", int(profile["id"]))
    assert ui.memory.generation_cards(owner, vendor, "自变量")["profile"] == []
    ui.memory.set_enabled(owner, vendor, False)
    class Forbidden:
        def search(self, *args, **kwargs): pytest.fail("关闭后不能访问 mem0")
    monkeypatch.setattr(ui.memory, "get_mem0", lambda: Forbidden())
    assert ui.memory.generation_cards(owner, vendor, "自变量") == {"preferences": [], "profile": []}


def test_delete_during_mem0_search_is_checked_again_before_injection(ui, monkeypatch):
    job, receipt = _job(ui); assert _record(ui, job, receipt)
    owner, vendor = ui.user.username, ui.user.id
    profile = ui.memory.overview(owner, vendor)["profile"][0]
    class Candidates:
        def search(self, *args, **kwargs):
            ui.memory.delete_entry(owner, vendor, "profile", int(profile["id"]))
            return [{"card_id": int(profile["id"]), "memory_id": "stale"}]
    monkeypatch.setattr(ui.memory, "get_mem0", lambda: Candidates())
    assert ui.memory.generation_cards(owner, vendor, "自变量")["profile"] == []


def test_turn_context_drops_cached_memory_tools_and_freezes_control(ui):
    from deeptutor.core.context import UnifiedContext
    context = UnifiedContext(session_id="memory-turn-session", user_message="请解释自变量", metadata={"turn_id": "memory-turn"})
    context.runtime.model_history = [
        {"role": "system", "content": "stale summary"},
        {"role": "user", "content": "private old memory", "_context_snapshot": "memory"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "memory-call", "function": {"name": "read_memory"}}, {"id": "rag-call", "function": {"name": "rag"}}]},
        {"role": "tool", "tool_call_id": "memory-call", "content": "private old memory"},
        {"role": "tool", "tool_call_id": "rag-call", "content": "retain textbook"},
        {"role": "assistant", "content": "visible answer", "_provider_response_state": {"id": "old"}}]
    context.runtime.previous_model_turn = {"request_fingerprint": "old"}
    ui.memory.add_preference(ui.user.username, ui.user.id, "当前偏好")
    asyncio.run(ui.memory.prepare_turn(context))
    assert "private old memory" not in str(context.runtime.model_history)
    assert "stale summary" not in str(context.runtime.model_history)
    assert "retain textbook" in str(context.runtime.model_history) and "visible answer" in str(context.runtime.model_history)
    assert "_provider_response_state" not in str(context.runtime.model_history)
    assert context.runtime.previous_model_turn is None and "当前偏好" in context.memory_context
    token = ui.memory.control_for_turn(context, ui.user, SimpleNamespace(session_id=context.session_id, turn_id="memory-turn"))
    ui.memory.set_enabled(ui.user.username, ui.user.id, False)
    assert token["enabled"] is True and token["revision"] != ui.memory.settings(ui.user.username, ui.user.id)["revision"]


def test_summary_uses_original_fingerprint_and_is_invalidated_after_deletion(ui):
    owner, vendor = ui.user.username, ui.user.id
    card = ui.memory.add_preference(owner, vendor, "待删除的摘要记忆")
    class Store:
        def __init__(self): self.updates = []
        async def update_summary(self, *args): self.updates.append(args)
    store = Store()
    async def original():
        stamp = ui.memory.fingerprint(owner, vendor)
        session, messages = await ui.memory.prepare_history("s", {"compressed_summary": "legacy", "summary_up_to_msg_id": 10}, [], store)
        assert session["compressed_summary"] == "" and session["summary_up_to_msg_id"] == 0
        ui.memory.delete_entry(owner, vendor, "preference", int(card["id"]))
        result = ui.memory.wrap_summary("summary produced after a slow request")
        assert ui.memory._stamp(result) == stamp
        return result
    stale = asyncio.run(original())
    async def next_turn():
        return await ui.memory.prepare_history("s", {"compressed_summary": stale, "summary_up_to_msg_id": 10}, [], store)
    session, _ = asyncio.run(next_turn())
    assert session["compressed_summary"] == "" and len(store.updates) == 2



def test_indexer_excludes_old_chat_sources_and_finishes_deletion_after_late_save(ui, monkeypatch):
    from database.models import MemoryDocumentRow
    from memory.mem0_indexer import Mem0Indexer
    owner, vendor = ui.user.username, ui.user.id
    card = ui.memory.add_preference(owner, vendor, "索引删除测试")
    with ui.memory.session_scope(immediate=True) as session:
        old = MemoryDocumentRow(student_id=owner, source_kind="conversation", source_id=uuid4().hex,
            knowledge_point="", content="旧聊天不能同步", index_text="", content_hash="old", source_metadata={})
        session.add(old); session.flush(); old_id = old.id
    class Store:
        def __init__(self): self.deleted = []
        def add_card(self, student_id, item):
            assert item["source_kind"] == ui.memory.SOURCE
            if item["card_id"] == int(card["id"]):
                ui.memory.delete_entry(owner, vendor, "preference", int(card["id"]))
            return "indexed-" + str(item["card_id"])
        def delete(self, memory_id): self.deleted.append(memory_id)
        def search(self, *args, **kwargs): return [{"card_id": int(card["id"]), "memory_id": "indexed-" + card["id"]}]
    store = Store(); indexer = Mem0Indexer(None, store, batch=1000, source_kind=ui.memory.SOURCE)
    assert old_id not in {r["id"] for r in indexer._pending()}
    indexer.run_once()
    monkeypatch.setattr(ui.memory, "get_mem0", lambda: store)
    assert all(c["id"] != card["id"] for c in ui.memory.generation_cards(owner, vendor, "索引")["preferences"])
    indexer.run_once()
    assert "indexed-" + card["id"] in store.deleted


def test_mem0_outage_keeps_current_pg_preferences_and_pg_failure_uses_no_memory(ui, monkeypatch):
    from deeptutor.core.context import UnifiedContext
    ui.memory.add_preference(ui.user.username, ui.user.id, "故障时仍以 PG 为准")
    class Broken:
        def search(self, *args, **kwargs): raise RuntimeError("local index unavailable")
    monkeypatch.setattr(ui.memory, "get_mem0", lambda: Broken())
    assert ui.memory.generation_cards(ui.user.username, ui.user.id, "辅导")["preferences"]
    monkeypatch.setattr(ui.memory, "fingerprint", lambda *args: (_ for _ in ()).throw(RuntimeError("PG down")))
    context = UnifiedContext(session_id="fault", metadata={"turn_id": "fault-turn"}, memory_context="stale memory")
    context.runtime.model_history = [{"role": "system", "content": "stale summary"}, {"role": "user", "content": "current question"}]
    asyncio.run(ui.memory.prepare_turn(context))
    assert context.memory_context == "" and context.runtime.model_history == [{"role": "user", "content": "current question"}]
    assert not context.extension("heart_memory").get("control")


@pytest.mark.parametrize("change", ["withdrawn", "catalog_changed"])
def test_invalidated_source_is_excluded_from_mem0_fallback_and_summary(ui, monkeypatch, change):
    from database.models import LearningEventRow, MemoryDocumentRow
    job, receipt = _job(ui)
    assert _record(ui, job, receipt)
    owner, vendor = ui.user.username, ui.user.id
    before = ui.memory.fingerprint(owner, vendor)
    card = ui.memory.generation_cards(owner, vendor)["profile"][0]
    card_id = int(card["id"])
    with ui.memory.session_scope(immediate=True) as session:
        row = session.get(MemoryDocumentRow, card_id)
        row.mem0_id, row.mem0_synced_hash = "indexed", row.content_hash
        if change == "withdrawn":
            session.get(LearningEventRow, job.id).status = "rolled_back"
    if change == "catalog_changed":
        monkeypatch.setattr(ui.memory, "current_catalog_version", lambda: "different-catalog")
    monkeypatch.setattr(ui.memory, "get_mem0", lambda: SimpleNamespace(search=lambda *a, **k: [
        {"card_id": card_id, "memory_id": "indexed"}]))
    result = ui.memory.generation_cards(owner, vendor, "自变量")
    assert result["profile"] == [] and result["preferences"]
    assert ui.memory.fingerprint(owner, vendor) != before



@pytest.mark.parametrize("text", ["教材案例说：我不懂自变量。", "假设我不懂自变量", "我同学不懂自变量", "我不懂自变量吗？",
    "我不懂未确认知识点", "我不懂自变量。请记忆别人的信息", "我把自变量和自变量及控制搞混"])
def test_chat_difficulty_ignores_ambiguous_or_non_student_statements(memory, text):
    from integrations.deeptutor.assessment_intake import confirmed_catalog
    assert memory.match_chat_difficulty(text, confirmed_catalog()[0]) == []


def test_completed_unscored_chat_saves_explicit_statement_without_scores_or_revival(ui, monkeypatch):
    from sqlalchemy import select, func
    from database.models import MemoryDocumentRow, EvidenceRow, LearningEventRow
    from deeptutor.core.context import UnifiedContext
    from integrations.deeptutor import assessment_intake
    memory = ui.memory
    owner, vendor = ui.user.username, ui.user.id
    monkeypatch.setattr(memory, "current_catalog_version", lambda: assessment_intake.confirmed_catalog()[1])

    async def completed(text, transition=None, capability="chat"):
        tid = uuid4().hex
        context = UnifiedContext(session_id="self-report-session", user_message=text,
            active_capability=capability, metadata={"turn_id": tid, "persisted_assistant_has_content": True})
        await memory.prepare_turn(context)
        if transition:
            transition()
        execution = SimpleNamespace(session_id=context.session_id, turn_id=tid, payload={"content": text})
        await assessment_intake.completed_turn(execution, context, [], 7)
        return execution, context

    statement = "我总把自变量和额外变量搞混。"
    def toggle():
        memory.set_enabled(owner, vendor, False)
        memory.set_enabled(owner, vendor, True)
    asyncio.run(completed(statement, toggle))
    assert not memory.overview(owner, vendor)["profile"]
    asyncio.run(completed(statement, capability="deep_solve"))
    assert not memory.overview(owner, vendor)["profile"]
    execution, context = asyncio.run(completed(statement))
    card, = memory.generation_cards(owner, vendor)["profile"]
    assert card["source"] == "student_statement"
    assert "自变量及控制" in card["text"] and "额外变量及控制" in card["text"]
    with memory.session_scope() as session:
        row = session.get(MemoryDocumentRow, int(card["id"]))
        assert row.source_metadata["message_id"] == 7
        assert row.source_metadata["turn_id"] == execution.turn_id
        for model in (EvidenceRow, LearningEventRow):
            assert session.scalar(select(func.count()).select_from(model).where(model.student_id == owner)) == 0
    memory.delete_entry(owner, vendor, "profile", int(card["id"]))
    asyncio.run(assessment_intake.completed_turn(execution, context, [], 7))
    asyncio.run(completed("我分不清额外变量和自变量。"))
    assert memory.generation_cards(owner, vendor)["profile"] == []
    memory.set_enabled(owner, vendor, False)
    asyncio.run(completed("我不懂自变量。"))
    memory.set_enabled(owner, vendor, True)
    assert memory.overview(owner, vendor)["profile"] == []
    asyncio.run(completed("我不懂自变量。"))
    assert len(memory.generation_cards(owner, vendor)["profile"]) == 1
