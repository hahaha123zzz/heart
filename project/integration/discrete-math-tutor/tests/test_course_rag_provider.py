"""固定教材普通检索：原生回合默认走宿主常驻 LightRAG，失败不静默回旧引擎。"""
import asyncio
from types import SimpleNamespace

from integrations.deeptutor import course_rag_provider as provider
from integrations.deeptutor import learning_tool_adapter
from integrations.deeptutor.native_contract import NativeTaskCheck


def _check():
    return NativeTaskCheck(
        student_id="s", course_id="experimental-psychology-3", session_id="sess",
        request_id="req", task_id="task", task_revision=1, memory_epoch=0,
        material_versions={"doc": "a" * 64})


def _source():
    return {
        "index": 1, "short_id": "S1", "rag_source_id": "r1", "chapter_id": 1, "page": 3,
        "section_id": 1, "document_id": "doc", "version": "a" * 64,
        "text": "自变量是研究者操纵的变量。", "quote": "自变量是研究者操纵的变量。",
        "location": {"section": "第一节", "block_start": 1, "block_end": 1},
    }


def _context():
    return SimpleNamespace(metadata={})


def _patch_search(monkeypatch, *, fail_status=None, payloads=None, sources=None):
    monkeypatch.setattr(learning_tool_adapter, "current_learning_context",
                        lambda: SimpleNamespace(check=_check()))
    sent = payloads if payloads is not None else []
    returned = sources if sources is not None else [_source()]

    class Backend:
        def __init__(self, base_url=None):
            self.base_url = base_url

        async def native_course_search(self, payload):
            return await self._answer(payload)

        async def native_user_course_search(self, payload):
            return await self._answer(payload)

        async def _answer(self, payload):
            sent.append(payload)
            if fail_status:
                from integrations.deeptutor.client import BackendUnavailable
                error = BackendUnavailable("host unavailable")
                error.status = fail_status
                raise error
            return {"status": "success", "sources": returned,
                    "usage": {}, "trace": [], "source_binding": {}}

    import integrations.deeptutor.client as client
    monkeypatch.setattr(client, "DeepTutorBackend", Backend)
    return sent


def _patch_verification(monkeypatch):
    import knowledge.lightrag.retrieval as retrieval

    monkeypatch.setattr(retrieval, "as_textbook_chunk", lambda row: row)
    monkeypatch.setattr("integrations.deeptutor.native_grounding.prepare_retrieval",
                        lambda query, chunks, context, kb: list(chunks))


def test_search_course_uses_host_lightrag_with_naive_default(monkeypatch):
    payloads = _patch_search(monkeypatch)
    _patch_verification(monkeypatch)

    result = asyncio.run(provider.search_course("自变量是什么", limit=5, context=_context()))

    assert payloads[0]["mode"] == "naive"
    assert payloads[0]["limit"] == 5
    assert payloads[0]["task_id"] == "task"
    assert payloads[0]["student_id"] == "s"
    assert result["backend"] == "lightrag"
    assert result["mode"] == "naive"
    assert result["cache_hit"] is False
    assert result["sources"][0]["text"] == "自变量是研究者操纵的变量。"


def test_search_course_uses_native_user_binding_without_task_scope(monkeypatch):
    sent = _patch_search(monkeypatch)
    _patch_verification(monkeypatch)
    from deeptutor.multi_user import context as user_context, learning_access
    from deeptutor.services.workspace import context as workspace_context

    monkeypatch.setattr(learning_access, "learning_material_allowed", lambda material_id: True)
    monkeypatch.setattr(learning_tool_adapter, "current_learning_context", lambda: None)
    monkeypatch.setattr(user_context, "get_current_user_or_none",
                        lambda: SimpleNamespace(id="u_1", username="heart-review-01", is_admin=False))
    monkeypatch.setattr(workspace_context, "current_workspace_id", lambda: "ws_1")

    context = SimpleNamespace(metadata={}, session_id="sess-1")
    result = asyncio.run(provider.search_course("自变量是什么", context=context))

    assert result["backend"] == "lightrag"
    assert sent[0]["student_id"] == "u_1"
    assert sent[0]["username"] == "heart-review-01"
    assert sent[0]["course_id"] == "experimental-psychology-3"
    assert sent[0]["session_id"] == "sess-1"
    assert sent[0]["workspace_id"] == "ws_1"
    assert sent[0]["request_id"]
    assert "task_id" not in sent[0] and "material_versions" not in sent[0]


def test_search_course_has_no_native_binding_without_session(monkeypatch):
    _patch_search(monkeypatch)
    from deeptutor.multi_user import context as user_context
    from deeptutor.services.workspace import context as workspace_context

    monkeypatch.setattr(learning_tool_adapter, "current_learning_context", lambda: None)
    monkeypatch.setattr(user_context, "get_current_user_or_none",
                        lambda: SimpleNamespace(id="u_1", username="heart-review-01", is_admin=False))
    monkeypatch.setattr(workspace_context, "current_workspace_id", lambda: "ws_1")

    assert asyncio.run(provider.search_course(
        "自变量是什么", context=SimpleNamespace(metadata={}, session_id=""))) is None


def test_search_course_reuses_turn_cache_and_merges_duplicate_sources(monkeypatch):
    payloads = _patch_search(monkeypatch)
    _patch_verification(monkeypatch)
    context = _context()

    first = asyncio.run(provider.search_course("自变量是什么", context=context))
    second = asyncio.run(provider.search_course("自变量是什么", context=context))

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["content"].startswith("本轮已返回相同教材原文")
    assert len(payloads) == 1
    assert second["sources"][0]["text"] == "自变量是研究者操纵的变量。"


def test_search_course_reports_not_ready_without_querying_old_engine(monkeypatch):
    payloads = _patch_search(monkeypatch, fail_status=503)

    result = asyncio.run(provider.search_course("自变量是什么", context=_context()))

    assert result["error_type"] == "not_ready"
    assert result["sources"] == []
    assert len(payloads) == 1


def _with_learner(monkeypatch, allowed_material):
    from deeptutor.multi_user import context as user_context, learning_access
    from knowledge import pdf_reader

    monkeypatch.setattr(pdf_reader, "document_for_chapter",
                        lambda chapter: {"version": ("a" if chapter == 1 else "b") * 64})
    monkeypatch.setattr(learning_access, "learning_material_allowed",
                        lambda material_id: material_id == allowed_material)
    token = user_context.set_current_user(
        SimpleNamespace(username="learner", id="learner-id", is_admin=False))
    return lambda: user_context.reset_current_user(token)


def test_search_course_drops_sources_from_unassigned_chapters(monkeypatch):
    unauthorized = {**_source(), "chapter_id": 4, "version": "b" * 64,
                    "document_id": "doc-4", "rag_source_id": "r4", "index": 2,
                    "text": "第四章未授权原文", "quote": "第四章未授权原文"}
    _patch_search(monkeypatch, sources=[_source(), unauthorized])
    _patch_verification(monkeypatch)
    restore = _with_learner(monkeypatch, "a" * 16)
    try:
        result = asyncio.run(provider.search_course("自变量是什么", context=_context()))
    finally:
        restore()

    assert [source["chapter_id"] for source in result["sources"]] == [1]
    assert all("未授权原文" not in source["text"] for source in result["sources"])


def test_search_course_reports_permission_when_all_sources_are_unassigned(monkeypatch):
    unauthorized = {**_source(), "chapter_id": 4, "version": "b" * 64,
                    "document_id": "doc-4", "rag_source_id": "r4",
                    "text": "第四章未授权原文", "quote": "第四章未授权原文"}
    _patch_search(monkeypatch, sources=[unauthorized])
    _patch_verification(monkeypatch)
    restore = _with_learner(monkeypatch, "a" * 16)
    try:
        result = asyncio.run(provider.search_course("第四章讲什么", context=_context()))
    finally:
        restore()

    assert result["error_type"] == "permission"
    assert result["sources"] == []


def test_search_course_maps_failed_verification_to_no_evidence(monkeypatch):
    _patch_search(monkeypatch)
    import knowledge.lightrag.retrieval as retrieval
    monkeypatch.setattr(retrieval, "as_textbook_chunk", lambda row: row)

    def reject(*args):
        raise ValueError("quote not locatable")

    monkeypatch.setattr("integrations.deeptutor.native_grounding.prepare_retrieval", reject)

    result = asyncio.run(provider.search_course("自变量是什么", context=_context()))

    assert result["error_type"] == "no_evidence"
    assert result["sources"] == []


def test_search_course_maps_host_timeout_and_permission(monkeypatch):
    for status, error_type in ((504, "timeout"), (403, "permission")):
        _patch_search(monkeypatch, fail_status=status)
        result = asyncio.run(provider.search_course("自变量是什么", context=_context()))
        assert result["error_type"] == error_type, status


def test_rag_tool_reports_backend_failure_instead_of_fabricating(monkeypatch):
    from integrations.deeptutor import heart_rag

    async def failed(*args, **kwargs):
        return {"error_type": "timeout", "sources": []}

    monkeypatch.setattr(provider, "search_course", failed)
    result = asyncio.run(heart_rag.HeartCourseRagTool().execute(query="自变量是什么"))

    assert result.success is False
    assert "超时" in result.content
    assert "不要编造依据" in result.content


def test_rag_tool_formats_lightrag_sources_with_citation(monkeypatch):
    from integrations.deeptutor import heart_rag

    async def found(*args, **kwargs):
        return {"sources": [_source()], "backend": "lightrag", "mode": "naive",
                "cache_hit": False}

    monkeypatch.setattr(provider, "search_course", found)
    monkeypatch.setattr(heart_rag, "_reader_citation", lambda source: "[教材第1章第3页](#dt-material-x)")
    result = asyncio.run(heart_rag.HeartCourseRagTool().execute(query="自变量是什么"))

    assert "[S1]" in result.content
    assert "自变量是研究者操纵的变量。" in result.content
    assert "[教材第1章第3页](#dt-material-x)" not in result.content
    assert result.metadata["mode"] == "naive"
    assert result.sources[0]["reader_citation"] == "[教材第1章第3页](#dt-material-x)"
    assert result.sources[0]["short_id"] == "S1"


def test_evidence_projection_keeps_whole_items_within_budget():
    long_text = "自变量" * 200
    sources = [
        {"index": 1, "short_id": "S1", "chapter_id": 1, "page": 3,
         "location": {"section": "第一节"}, "rag_source_id": "r1", "text": "A" * 300},
        {"index": 2, "short_id": "S2", "chapter_id": 2, "page": 9,
         "location": {"section": "第二节"}, "rag_source_id": "r2", "text": "B" * 300},
    ]
    content = provider.source_content(sources, budget_chars=600)

    assert "[S1]" in content and "A" * 300 in content
    assert "B" * 300 not in content
    assert "read_source 读取 S2" in content
    assert "[S2] 第2章，第9页" in content


def test_rag_tool_does_not_resend_passages_on_turn_cache_hit(monkeypatch):
    from integrations.deeptutor import heart_rag

    async def cached(*args, **kwargs):
        return {"sources": [_source()], "backend": "lightrag", "mode": "naive",
                "cache_hit": True, "content": "本轮已返回相同教材原文（引用编号不变）：[1]"}

    monkeypatch.setattr(provider, "search_course", cached)
    result = asyncio.run(heart_rag.HeartCourseRagTool().execute(query="自变量是什么"))

    assert "本轮已返回相同教材原文" in result.content
    assert "已核验原文" not in result.content


def test_rag_tool_refuses_when_no_source_can_be_linked(monkeypatch):
    from integrations.deeptutor import heart_rag

    async def found(*args, **kwargs):
        return {"sources": [_source()], "backend": "lightrag", "mode": "naive"}

    monkeypatch.setattr(provider, "search_course", found)
    monkeypatch.setattr(heart_rag, "_reader_citation", lambda source: "")
    result = asyncio.run(heart_rag.HeartCourseRagTool().execute(query="自变量是什么"))

    assert result.success is False
    assert "不提供引用" in result.content


def test_rag_tool_allows_more_than_two_searches_per_turn(monkeypatch):
    from integrations.deeptutor import heart_rag

    calls = []

    async def found(*args, **kwargs):
        calls.append(1)
        return {"sources": [_source()], "backend": "lightrag", "mode": "naive"}

    monkeypatch.setattr(provider, "search_course", found)
    monkeypatch.setattr(heart_rag, "_reader_citation", lambda source: "[教材第1章第3页](#dt-material-x)")
    context = SimpleNamespace(metadata={})
    tool = heart_rag.HeartCourseRagTool()
    asyncio.run(tool.execute(query="自变量是什么", _heart_context=context))
    asyncio.run(tool.execute(query="那暂时性被试自变量呢", _heart_context=context))
    third = asyncio.run(tool.execute(query="再查一次", _heart_context=context))

    assert len(calls) == 3
    assert third.success is True
    assert len(third.sources) == 1


def test_rag_tool_keeps_local_index_only_when_no_native_scope(monkeypatch):
    from integrations.deeptutor import heart_rag

    async def unscoped(*args, **kwargs):
        return None

    monkeypatch.setattr(provider, "search_course", unscoped)
    monkeypatch.setattr(heart_rag, "_verified_sources", lambda *_: [_source()])
    monkeypatch.setattr(heart_rag, "_reader_citation", lambda source: "[教材第1章第3页](#dt-material-x)")
    result = asyncio.run(heart_rag.HeartCourseRagTool().execute(query="自变量是什么"))

    assert result.success is True
    assert "[S1]" in result.content
    assert result.sources[0]["reader_citation"] == "[教材第1章第3页](#dt-material-x)"


def _endpoint(monkeypatch, backend):
    from integrations.deeptutor import native_authorization
    from knowledge import fixed_book

    monkeypatch.setattr(fixed_book, "active",
                        lambda: None if backend is None else SimpleNamespace(backend=backend))
    authorized = []
    monkeypatch.setattr(native_authorization, "authorize_native_task",
                        lambda payload: authorized.append(payload) or {"authorized": True})
    return authorized


def _endpoint_payload(**kwargs):
    from integrations.deeptutor.native_contract import CourseSearchRequest

    return CourseSearchRequest(**_check().model_dump(), query="自变量是什么", **kwargs)


def test_course_search_endpoint_authorizes_and_queries_requested_mode(monkeypatch):
    from integrations.deeptutor import course_search_api as api

    class Backend:
        def __init__(self):
            self.calls = []

        async def search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            return {"provider": "lightrag", "sdk": "1.5.7", "status": "success",
                    "mode": kwargs["mode"], "sources": [], "usage": {}, "trace": [],
                    "source_binding": {}}

    backend = Backend()
    authorized = _endpoint(monkeypatch, backend)
    result = asyncio.run(api.course_search(_endpoint_payload(mode="naive", limit=6), None))

    assert len(authorized) == 2
    assert backend.calls[0]["mode"] == "naive"
    assert backend.calls[0]["limit"] == 6
    assert backend.calls[0]["course_id"] == "experimental-psychology-3"
    assert result["status"] == "success"


def test_course_search_endpoint_does_not_query_before_authorization(monkeypatch):
    from fastapi import HTTPException
    from integrations.deeptutor import course_search_api as api
    from integrations.deeptutor import native_authorization

    class Backend:
        calls = 0

        async def search(self, *args, **kwargs):
            Backend.calls += 1
            return {}

    _endpoint(monkeypatch, Backend())

    def reject(payload):
        raise HTTPException(409, detail={"code": "source_changed"})

    monkeypatch.setattr(native_authorization, "authorize_native_task", reject)
    try:
        asyncio.run(api.course_search(_endpoint_payload(), None))
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("授权失败必须拒绝查询")
    assert Backend.calls == 0


def test_course_search_endpoint_reports_not_ready_and_timeout(monkeypatch):
    from fastapi import HTTPException
    from integrations.deeptutor import course_search_api as api

    _endpoint(monkeypatch, None)
    try:
        asyncio.run(api.course_search(_endpoint_payload(), None))
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("后端未就绪必须返回 503")

    class SlowBackend:
        async def search(self, *args, **kwargs):
            await asyncio.sleep(3600)

    backend = SlowBackend()
    monkeypatch.setattr(api, "QUERY_BUDGET_SECONDS", 0.01)
    _endpoint(monkeypatch, backend)
    try:
        asyncio.run(api.course_search(_endpoint_payload(), None))
    except HTTPException as exc:
        assert exc.status_code == 504
    else:
        raise AssertionError("超出预算必须返回 504")


def _native_endpoint_payload():
    from integrations.deeptutor.native_contract import NativeUserCourseSearchRequest

    return NativeUserCourseSearchRequest(
        student_id="u_1", username="heart-review-01",
        course_id="experimental-psychology-3", session_id="sess-1",
        workspace_id="ws-1", request_id="req-1", query="自变量是什么")


def test_native_course_search_filters_unassigned_versions(monkeypatch):
    from integrations.deeptutor import course_search_api as api

    class Backend:
        async def search(self, query, **kwargs):
            return {"provider": "lightrag", "sdk": "1.5.7", "status": "success",
                    "mode": kwargs["mode"],
                    "sources": [_source(), {**_source(), "version": "b" * 64,
                                            "document_id": "doc-2", "index": 2}],
                    "usage": {}, "trace": [], "source_binding": {}}

    _endpoint(monkeypatch, Backend())

    async def scope(payload):
        return ({"a" * 16},
                {"preferences": {"workspace_id": payload.workspace_id}},
                {"id": "turn-1"})

    monkeypatch.setattr(api, "_native_scope", scope)
    result = asyncio.run(api.course_search_native(_native_endpoint_payload(), None))

    assert [source["version"] for source in result["sources"]] == ["a" * 64]


def test_native_course_search_rejects_expired_turn_and_unauthorized_material(monkeypatch):
    from fastapi import HTTPException
    from integrations.deeptutor import course_search_api as api

    _endpoint(monkeypatch, None)

    async def expired(payload):
        return (None, None, None)

    monkeypatch.setattr(api, "_native_scope", expired)
    try:
        asyncio.run(api.course_search_native(_native_endpoint_payload(), None))
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("失效会话必须拒绝")

    class Backend:
        async def search(self, query, **kwargs):
            return {"provider": "lightrag", "sdk": "1.5.7", "status": "success",
                    "mode": kwargs["mode"], "sources": [_source()],
                    "usage": {}, "trace": [], "source_binding": {}}

    _endpoint(monkeypatch, Backend())

    async def none_allowed(payload):
        return (set(), {"preferences": {"workspace_id": payload.workspace_id}}, {"id": "turn-1"})

    monkeypatch.setattr(api, "_native_scope", none_allowed)
    try:
        asyncio.run(api.course_search_native(_native_endpoint_payload(), None))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("未授权材料必须拒绝")


def test_native_policy_reads_assigned_material_versions(monkeypatch):
    from fastapi import HTTPException
    from integrations.deeptutor import course_search_api as api
    from deeptutor.multi_user import learning_access

    monkeypatch.setattr(learning_access, "learning_policy_for_user",
                        lambda *a, **k: {"allowed_surfaces": ["chat"],
                                         "reading": {"material_ids": ["a" * 16]}})
    assert api._native_policy("u_1", False) == {"a" * 16}

    monkeypatch.setattr(learning_access, "learning_policy_for_user",
                        lambda *a, **k: {"allowed_surfaces": ["reading"]})
    try:
        api._native_policy("u_1", False)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("未开放聊天面的账号必须拒绝")


def test_client_rejects_malformed_course_search_response(monkeypatch):
    import httpx
    from integrations.deeptutor.client import BackendUnavailable, DeepTutorBackend

    class Response:
        status_code = 200

        def json(self):
            return {"status": "success"}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setenv("DEEPTUTOR_BRIDGE_TOKEN", "x" * 40)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    try:
        asyncio.run(DeepTutorBackend("http://127.0.0.1:8000").native_course_search({"query": "x"}))
    except BackendUnavailable:
        pass
    else:
        raise AssertionError("缺少 sources 的响应必须被拒绝")


def test_search_course_cancellation_reaches_the_host_request(monkeypatch):
    monkeypatch.setattr(learning_tool_adapter, "current_learning_context",
                        lambda: SimpleNamespace(check=_check()))
    released = asyncio.Event()

    class Backend:
        def __init__(self, base_url=None):
            pass

        async def native_course_search(self, payload):
            try:
                await asyncio.sleep(3600)
            finally:
                released.set()

    import integrations.deeptutor.client as client
    monkeypatch.setattr(client, "DeepTutorBackend", Backend)

    async def scenario():
        task = asyncio.create_task(
            provider.search_course("自变量是什么", context=_context()))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("取消必须向上传播")
        # 不依赖 asyncio.run 关闭循环时的兜底清理。
        await asyncio.sleep(0.05)
        assert released.is_set()

    asyncio.run(scenario())
