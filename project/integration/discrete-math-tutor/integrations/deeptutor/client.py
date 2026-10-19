"""本机后端边界：只读目录及服务端限定的会话绑定。"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class BackendUnavailable(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class DeepTutorBackend:
    def __init__(self, base_url: str | None = None, timeout: float = 3):
        value = base_url if base_url is not None else os.getenv("DEEPTUTOR_BACKEND_URL", "http://127.0.0.1:18001")
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("DeepTutor 本机服务端口无效") from exc
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"} or not port):
            raise ValueError("DEEPTUTOR_BACKEND_URL 必须是带端口的本机 HTTP 服务地址")
        self.base_url = value.rstrip("/")
        self.timeout = timeout
        # 本机通信不经过系统代理，避免代理转发本地服务请求。
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _get(self, path: str) -> dict:
        request = Request(self.base_url + path, headers={"Accept": "application/json"})
        return self._send(request)

    def _send(self, request: Request) -> dict:
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError("响应超过限制")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("响应不是对象")
            return result
        except (OSError, ValueError) as exc:
            raise BackendUnavailable("DeepTutor 后端暂未就绪") from exc

    def bind_session(self, student_id: str, session_id: str) -> dict:
        from knowledge.course_config import COURSE_ID, COURSE_TITLE

        payload = {"student_id": student_id, "session_id": session_id,
                   "course_id": COURSE_ID, "course_title": COURSE_TITLE}
        self.timeout = max(self.timeout, 25)
        result = self._post("/internal/heart/session", payload)
        if (any(not isinstance(result.get(key), str) or not result[key] or len(result[key]) > 100
                for key in ("user_id", "course_id", "session_id")) or result.get("role") != "student"):
            raise BackendUnavailable("DeepTutor 会话映射响应无效")
        return {key: result[key] for key in ("user_id", "course_id", "session_id", "role")}

    def _post(self, path: str, payload: dict) -> dict:
        token = os.getenv("DEEPTUTOR_BRIDGE_TOKEN", "")
        if len(token) < 32:
            raise BackendUnavailable("DeepTutor 宿主接入凭据未配置")
        return self._send(Request(self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "X-Heart-Bridge-Token": token}))

    def publish_turn(self, projection: dict) -> dict:
        result = self._post("/internal/heart/turn", projection)
        if (result.get("task_id") != projection["task_id"]
                or result.get("task_revision") != projection["task_revision"]
                or not isinstance(result.get("turn_id"), str) or not result["turn_id"]
                or result.get("last_seq") != 2):
            raise BackendUnavailable("DeepTutor 回合响应无效")
        return {key: result[key] for key in ("turn_id", "last_seq", "task_id", "task_revision")}

    def turn_events(self, cursor: dict) -> dict:
        result = self._post("/internal/heart/turn/events", cursor)
        if not isinstance(result.get("events"), list) or len(result["events"]) > 2:
            raise BackendUnavailable("DeepTutor 回合事件响应无效")
        return result

    def generate(self, messages, *, model, temperature, max_tokens, timeout=None, reasoning_effort=None):
        deadline = min(timeout if timeout is not None else 120, 180)
        self.timeout = deadline + 5
        result = self._post("/internal/heart/generate", {"messages": messages, "model": model,
            "temperature": temperature, "max_tokens": max_tokens, "timeout": deadline,
            "reasoning_effort": reasoning_effort})
        if not isinstance(result.get("content"), str) or result.get("finish_reason") not in {"stop", "length"}:
            raise BackendUnavailable("DeepTutor 生成响应无效")
        return result["content"], result["finish_reason"]

    def status(self) -> dict:
        try:
            ready = self._get("/health/ready").get("status") == "ready"
            return {"connected": True, "backend_ready": ready, "model_execution_verified": False}
        except BackendUnavailable:
            return {"connected": False, "backend_ready": False, "model_execution_verified": False}

    def capabilities(self) -> list[dict]:
        items = self._get("/api/capabilities/registered").get("capabilities")
        if not isinstance(items, list):
            raise BackendUnavailable("DeepTutor 能力目录响应无效")
        result = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise BackendUnavailable("DeepTutor 能力目录响应无效")
            manifest = item.get("manifest")
            if not isinstance(manifest, dict):
                raise BackendUnavailable("DeepTutor 能力目录响应无效")
            result.append({"id": item["id"], "registered": True,
                           "description": str(manifest.get("description", "")),
                           "model_execution_verified": False})
        return result
