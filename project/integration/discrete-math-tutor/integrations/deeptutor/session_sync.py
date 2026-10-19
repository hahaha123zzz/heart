"""在原任务保存成功后绑定空会话；同步失败不撤销已核验的回答。"""
import os

from .client import BackendUnavailable, DeepTutorBackend


def sync_completed_session(request, result):
    if (os.getenv("DEEPTUTOR_SESSION_SYNC", "0") != "1"
            or result.get("answer_status") != "answered" or not result.get("conversation_id")):
        return result
    try:
        binding = DeepTutorBackend().bind_session(request.student_id, request.session_id)
        state = {"status": "ready", **binding}
    except (BackendUnavailable, ValueError):
        state = {"status": "unavailable"}
    return {**result, "deeptutor_session": state}
