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
        self.timeout = max(self.timeout, 25)
        result = self._post("/internal/heart/turn", projection)
        if (result.get("task_id") != projection["task_id"]
                or result.get("task_revision") != projection["task_revision"]
                or not isinstance(result.get("turn_id"), str) or not result["turn_id"]
                or result.get("last_seq") != 2):
            raise BackendUnavailable("DeepTutor 回合响应无效")
        return {key: result[key] for key in ("turn_id", "last_seq", "task_id", "task_revision")}

    def authorize_native_task(self, expected: dict) -> None:
        result = self._post('/internal/heart/native/authorize', expected)
        if result != {'authorized': True, **expected}:
            raise BackendUnavailable('宿主任务核验响应无效')

    def authorize_native_assessment(self, expected: dict) -> None:
        result = self._post('/internal/heart/native/authorize-assessment', expected)
        if result != {'authorized': True, **expected}:
            raise BackendUnavailable('宿主测评核验响应无效')

    def turn_events(self, cursor: dict) -> dict:
        result = self._post("/internal/heart/turn/events", cursor)
        if not isinstance(result.get("events"), list) or len(result["events"]) > 2:
            raise BackendUnavailable("DeepTutor 回合事件响应无效")
        return result

    def generate(self, messages, *, model, temperature, max_tokens, timeout=None, reasoning_effort=None, evidence=None, max_characters=None):
        deadline = min(timeout if timeout is not None else 120, 180)
        self.timeout = deadline + 5
        payload = {"messages": messages, "model": model,
            "temperature": temperature, "max_tokens": max_tokens, "timeout": deadline,
            "reasoning_effort": reasoning_effort}
        if evidence is not None:
            import hashlib
            payload["evidence"] = evidence
            if max_characters is not None:
                payload["max_characters"] = max_characters
        result = self._post("/internal/heart/agentic" if evidence is not None else "/internal/heart/generate", payload)
        if evidence is not None and (result.get("engine") != "agent_loop"
                or type(result.get("rounds")) is not int or not 2 <= result["rounds"] <= 6
                or type(result.get("tool_steps")) is not int or not 1 <= result["tool_steps"] <= 6
                or type(result.get("evidence_reads")) is not int or result["evidence_reads"] < 1
                or result.get("evidence_sha256") != hashlib.sha256(evidence.encode()).hexdigest()):
            raise BackendUnavailable("DeepTutor 执行链证据回执无效")
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

    def native_catalog(self, scope):
        self.timeout = max(self.timeout, 120)
        return self._post('/internal/heart/native/catalog', scope)

    def native_memory(self, payload):
        return self._post('/internal/heart/native/memory', payload)

    def native_prepare_reading(self, scope):
        self.timeout = max(self.timeout, 180)
        return self._post('/internal/heart/native/reading/prepare', scope)

    def native_start(self, payload):
        self.timeout = max(self.timeout, 180)
        return self._post('/internal/heart/native/start', payload)

    def native_status(self, key):
        return self._post('/internal/heart/native/status', key)

    def native_command(self, key, *, command_id, text=None):
        return self._post('/internal/heart/native/reply' if text is not None else '/internal/heart/native/cancel',
                          {**key, 'command_id': command_id, **({'text': text} if text is not None else {})})

    def native_events(self, key, *, after_seq=0):
        token = os.getenv('DEEPTUTOR_BRIDGE_TOKEN', '')
        if len(token) < 32:
            raise BackendUnavailable('DeepTutor 宿主接入凭据未配置')
        request = Request(self.base_url + '/internal/heart/native/events', method='POST',
            data=json.dumps({**key, 'after_seq': after_seq}, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json', 'Accept': 'application/x-ndjson',
                     'X-Heart-Bridge-Token': token})
        try:
            with self.opener.open(request, timeout=max(self.timeout, 30)) as response:
                while line := response.readline(4 * 1024 * 1024 + 1):
                    if len(line) > 4 * 1024 * 1024:
                        raise ValueError('原生事件超过限制')
                    value = json.loads(line)
                    if (not isinstance(value, dict) or value.get('engine') != 'deeptutor_app'
                            or not isinstance(value.get('event'), dict)):
                        raise ValueError('原生事件响应无效')
                    yield value['event']
        except (OSError, ValueError) as exc:
            raise BackendUnavailable('原生事件连接中断；可按原 turn 和游标恢复') from exc
