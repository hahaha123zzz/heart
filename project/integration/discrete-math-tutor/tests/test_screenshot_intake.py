"""截图识别使用真实持久回执与假模型，不访问供应商。"""
import asyncio
from types import SimpleNamespace

import pytest

from deeptutor.core.context import Attachment, UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from integrations.deeptutor import screenshot_intake as intake

READING = {"question_count": 1, "question": "实验中哪一个变量由研究者操纵？", "options": {"A": "自变量", "B": "因变量"},
    "question_complete": True, "student_answer": "A", "answer_origin": "student", "reference_answer": "", "solution_steps": "", "missing_fields": []}


@pytest.fixture
def screen(tmp_path, monkeypatch):
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.services import session
    user = SimpleNamespace(username="screen-owner", id="screen-vendor", is_admin=False)
    token = set_current_user(user)
    path = tmp_path / "screen.db"
    monkeypatch.setattr(session, "get_sqlite_session_store", lambda: SimpleNamespace(db_path=path))
    config = {"api_key": "private-screen-key", "model": "screen-model", "base_url": "https://public.example/v1", "credential_version": "screen-version"}
    monkeypatch.setattr(intake, "model_config", lambda _: dict(config))
    monkeypatch.setattr(intake, "failure_details", lambda _: {"error_code": "outcome_unknown", "message": "截图识别结果不明，可能已计费。"})
    calls = []
    async def recognize(config, text, images):
        calls.append((config["model"], text, images))
        return intake.ScreenshotReading.model_validate(READING).model_dump_json()
    monkeypatch.setattr(intake, "recognize", recognize)
    def context(turn="screen-turn"):
        return UnifiedContext(session_id="screen-session", user_message="这是我的作答，请帮我看看。",
            metadata={"turn_id": turn, "mastery_path_id": "screen-path"},
            attachments=[Attachment(type="image", id="screenshot-1", mime_type="image/png", base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")])
    yield SimpleNamespace(user=user, path=path, config=config, calls=calls, context=context)
    reset_current_user(token)


def run(context):
    async def collect():
        return [event async for event in intake.prepare_screenshot(context)]
    return asyncio.run(collect())


def test_auto_reader_and_historical_images_do_not_start_screenshot_intake(screen):
    context = screen.context()
    context.attachments[0].origin = "reading_viewport"
    context.attachments.append(Attachment(
        type="image", id="old-screenshot", origin="conversation_history",
        mime_type="image/png", base64="not-current-input",
    ))
    assert run(context) == []
    assert screen.calls == []


def test_current_explicit_image_is_recognized_without_historical_images(screen):
    context = screen.context()
    current = context.attachments[0]
    old = Attachment(type="image", id="old-screenshot", origin="conversation_history",
                     mime_type="image/png", base64="not-current-input")
    context.attachments = [old, current]
    run(context)
    assert len(screen.calls) == 1
    assert len(screen.calls[0][2]) == 1


def test_pdf_and_extracted_images_do_not_start_screenshot_intake(screen):
    context = screen.context()
    context.attachments = [
        Attachment(type="pdf", id="uploaded-pdf", origin="user_submission"),
        Attachment(type="image", id="extracted-figure", origin="document_extraction",
                   mime_type="image/png", base64="not-current-input"),
    ]
    assert run(context) == []
    assert screen.calls == []


def test_complete_screenshot_replays_without_calling_model_and_does_not_store_image_bytes(screen):
    context = screen.context()
    events = run(context)
    assert events[0].type == StreamEventType.PROGRESS
    assert "个人模型额度" in events[0].content
    assert "辅助学习" in events[-1].content
    receipt = intake.receipt_for(context, screen.user, SimpleNamespace(session_id="screen-session", turn_id="screen-turn"))
    assert receipt and receipt.reading.assisted
    assert "reference_answer" in context.user_message and "reference_answer" in context.sidebar_context
    run(screen.context())
    run(context)
    assert len(screen.calls) == 1
    with intake._connect(screen.path) as conn:
        row = dict(conn.execute("SELECT * FROM heart_screenshot_inputs").fetchone())
    assert row["status"] == "completed"
    assert "fixture-image-bytes" not in str(row) and "private-screen-key" not in str(row)
    assert "base64" not in str(row)


@pytest.mark.parametrize("change", [{"question_complete": False, "missing_fields": ["缺少选项 B"]},
    {"question_count": 2}, {"question": ""}, {"student_answer": "", "answer_origin": "unknown"}])
def test_incomplete_or_ambiguous_image_stops_before_tutoring(screen, monkeypatch, change):
    from deeptutor.runtime import turn_engine, orchestrator
    data = {**READING, **change}
    async def recognize(*args):
        screen.calls.append(1)
        return intake.ScreenshotReading.model_validate(data).model_dump_json()
    monkeypatch.setattr(intake, "recognize", recognize)
    monkeypatch.setattr(turn_engine, "_external_input_preparer", intake.prepare_screenshot)
    class ForbiddenOrchestrator:
        def __init__(self, **kwargs):
            pytest.fail("不完整截图不能进入辅导模型")
    monkeypatch.setattr(orchestrator, "ChatOrchestrator", ForbiddenOrchestrator)
    context = screen.context()
    async def collect():
        return [event async for event in turn_engine.TurnEngine().execute(context)]
    events = asyncio.run(collect())
    assert events[-1].type == StreamEventType.DONE
    assert "本次不评分" in events[-2].content
    assert not context.extension("heart_screenshot").get("receipt")
    run(screen.context())
    assert len(screen.calls) == 1


@pytest.mark.parametrize("failure", [TimeoutError(), ValueError("supplier-private-error")])
def test_unknown_or_invalid_response_is_never_automatically_resent(screen, monkeypatch, failure):
    async def broken(*args):
        screen.calls.append(1)
        raise failure
    monkeypatch.setattr(intake, "recognize", broken)
    first = run(screen.context())
    second = run(screen.context())
    assert len(screen.calls) == 1
    assert "不会自动重发" in first[-2].content and "不会自动重发" in second[-2].content
    assert "supplier-private-error" not in str(first)


def test_cancellation_after_send_keeps_durable_sent_marker(screen, monkeypatch):
    async def cancelled(*args):
        screen.calls.append(1)
        raise asyncio.CancelledError()
    monkeypatch.setattr(intake, "recognize", cancelled)
    with pytest.raises(asyncio.CancelledError):
        run(screen.context())
    events = run(screen.context())
    assert len(screen.calls) == 1 and "结果不明" in events[-2].content


def test_parallel_same_turn_uses_one_request_and_completed_replay_is_owner_bound(screen, monkeypatch):
    async def recognize(*args):
        screen.calls.append(1)
        await asyncio.sleep(0.01)
        return intake.ScreenshotReading.model_validate(READING).model_dump_json()
    monkeypatch.setattr(intake, "recognize", recognize)
    async def collect(context):
        return [event async for event in intake.prepare_screenshot(context)]
    async def concurrent():
        return await asyncio.gather(collect(screen.context()), collect(screen.context()))
    asyncio.run(concurrent())
    assert len(screen.calls) == 1
    changed = screen.context()
    changed.user_message = "a different submission"
    assert run(changed)[-1].type == StreamEventType.DONE
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    token = set_current_user(SimpleNamespace(username="other-owner", id="other-vendor", is_admin=False))
    try:
        events = run(screen.context())
        assert events[-1].type == StreamEventType.DONE
        assert "实验中" not in str(events)
    finally:
        reset_current_user(token)
    assert len(screen.calls) == 1


def test_missing_image_and_unverified_vision_never_send(screen, monkeypatch):
    context = screen.context()
    context.attachments[0].base64 = ""
    context.attachments[0].url = "/files/attachments/s/missing/expired.png"
    from deeptutor.services.llm import multimodal
    monkeypatch.setattr(multimodal, "_resolve_local_attachment_url", lambda _: None)
    assert "原图已不可用" in run(context)[-2].content
    monkeypatch.setattr(intake, "model_config", lambda _: None)
    assert "验证" in run(screen.context())[-2].content
    assert screen.calls == []


def test_question_only_image_does_not_claim_assistance_and_receipt_cannot_cross_turn(screen, monkeypatch):
    data = {**READING, "student_answer": "", "answer_origin": "none"}
    async def recognize(*args):
        return intake.ScreenshotReading.model_validate(data).model_dump_json()
    monkeypatch.setattr(intake, "recognize", recognize)
    context = screen.context()
    run(context)
    receipt = intake.receipt_for(context, screen.user, SimpleNamespace(session_id="screen-session", turn_id="screen-turn"))
    assert receipt and not receipt.reading.assisted
    assert intake.receipt_for(context, screen.user, SimpleNamespace(session_id="screen-session", turn_id="another-turn")) is None



def test_complete_image_continues_to_tutoring_after_showing_recognized_input(screen, monkeypatch):
    from deeptutor.runtime import turn_engine, orchestrator
    captured = []
    monkeypatch.setattr(turn_engine, "_external_input_preparer", intake.prepare_screenshot)
    class Tutor:
        async def handle(self, context):
            captured.append(context)
            assert context.extension("heart_screenshot")["receipt"].reading.ready
            assert "截图识别数据" in context.user_message
            assert "实验中哪一个变量" not in context.sidebar_context
            yield StreamEvent(type=StreamEventType.CONTENT, content="继续辅导")
            yield StreamEvent(type=StreamEventType.DONE)
    monkeypatch.setattr(orchestrator, "ChatOrchestrator", Tutor)
    async def collect():
        return [event async for event in turn_engine.TurnEngine().execute(screen.context())]
    events = asyncio.run(collect())
    assert len(captured) == 1 and len(screen.calls) == 1
    assert "截图识别的题目" in events[1].content
    assert events[2].content == "继续辅导" and events[-1].type == StreamEventType.DONE


@pytest.mark.parametrize(
    "raw",
    ["not json", '{"question_complete":"true"}', "x" * 65537],
    ids=["non-json", "wrong-field-type", "oversized-response"],
)
def test_invalid_structured_result_is_not_used_or_retried(screen, monkeypatch, raw):
    async def recognize(*args):
        screen.calls.append(1)
        return raw
    monkeypatch.setattr(intake, "recognize", recognize)
    context = screen.context()
    assert run(context)[-1].type == StreamEventType.DONE
    assert not context.extension("heart_screenshot").get("receipt")
    run(screen.context())
    assert len(screen.calls) == 1


def test_protocol_type_is_a_fixed_optional_marker_not_a_way_to_accept_extra_data():
    value=intake.ScreenshotReading.model_validate({**READING,"type":"json_object"})
    assert "type" not in value.model_dump() and value.ready
    with pytest.raises(ValueError):intake.ScreenshotReading.model_validate({**READING,"type":"untrusted"})
    with pytest.raises(ValueError):intake.ScreenshotReading.model_validate({**READING,"score":100})
