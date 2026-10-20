"""Single OpenAI-compatible model gateway for the discrete-math tutor."""

from __future__ import annotations

import json
import threading
import os
import re
import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from llm.mock_discrete import mock_reply


class LLMError(RuntimeError):
    """The configured model could not produce a usable answer."""


class LLMJSONError(LLMError):
    """模型已返回内容，但 JSON 结构不可解析。"""


@dataclass
class ChatToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str = ""


@dataclass
class ChatToolResult:
    text: str = ""
    tool_calls: list[ChatToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


def extract_json(text: str) -> Dict[str, Any]:
    """Accept a JSON object, optionally wrapped in a code fence."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.I)
    try:
        parsed = json.loads(stripped)
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回 JSON 对象") from None
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("模型返回的 JSON 顶层必须是对象")
    return parsed


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        mock: Optional[bool] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
        self.model = model or os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL", "deepseek-flash")
        self.vision_model = os.getenv("OPENAI_VISION_MODEL", "deepseek-flash")
        self.mock = (os.getenv("LLM_MOCK", "0") == "1") if mock is None else mock
        self._client = None
        self._client_lock = threading.Lock()

    def _client_lazy(self):
        with self._client_lock:
            if self._client is None:
                if not self.api_key:
                    raise LLMError("缺少 DeepSeek API Key；设置 DEEPSEEK_API_KEY，或使用 LLM_MOCK=1。")
                from openai import OpenAI
    
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def _one_call(
        self, messages: List[Dict[str, Any]], temperature: float, max_tokens: int,
        model: str | None = None, timeout: float | None = None,
        reasoning_effort: str | None = None,
    ) -> tuple[str, str | None]:
        if os.getenv("DEEPTUTOR_LLM_ENABLED", "0") == "1":
            from integrations.deeptutor.client import DeepTutorBackend
            return DeepTutorBackend().generate(messages, model=model or self.model,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout, reasoning_effort=reasoning_effort)
        args: dict[str, Any] = {
            "model": model or self.model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if reasoning_effort is not None:
            if reasoning_effort not in {"low", "high", "max"}:
                raise LLMError("不支持的 reasoning_effort")
            args["reasoning_effort"] = reasoning_effort
        if "api.deepseek.com" in self.base_url:
            args["extra_body"] = {"thinking": {"type": "enabled" if reasoning_effort else "disabled"}}
        client = self._client_lazy()
        if timeout is not None:
            client = client.with_options(timeout=timeout, max_retries=0)
        response = client.chat.completions.create(**args)
        choice = response.choices[0]
        return choice.message.content or "", choice.finish_reason

    @staticmethod
    def _with_images(messages: List[Dict[str, Any]], image_paths: List[Path]) -> List[Dict[str, Any]]:
        """仅将已核对的教材 PNG 附加到最后一条用户消息。"""
        from knowledge.figures import load_figures

        if not messages or messages[-1].get("role") != "user":
            raise LLMError("图片必须附在最后一条用户消息")
        result = [dict(message) for message in messages]
        content = result[-1].get("content")
        if not isinstance(content, str):
            raise LLMError("图片消息的文本内容无效")
        allowed = {figure.path.resolve(): figure for figure in load_figures()}
        parts: list[dict[str, Any]] = [{"type": "text", "text": content}]
        for image_path in image_paths[:2]:
            resolved = image_path.resolve()
            if resolved in allowed:
                valid = allowed[resolved].is_valid()
            else:
                from knowledge.pdf_reader import crop_path
                valid = crop_path(resolved.stem) == resolved
            if not valid:
                raise LLMError("图片不在已审核教材目录中")
            image = resolved.read_bytes()
            if len(image) > 8 * 1024 * 1024:
                raise LLMError("教材图片超过视觉输入限制")
            media_type = ("image/png" if resolved.suffix.lower() == ".png" else
                          "image/jpeg" if resolved.suffix.lower() in (".jpg", ".jpeg") else
                          "application/octet-stream")
            data_url = f"data:{media_type};base64," + base64.b64encode(image).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": data_url, "detail": "original"}})
        result[-1]["content"] = parts
        return result

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.4,
        max_tokens: int = 1200,
        image_paths: Optional[List[Path]] = None,
        timeout: float | None = None,
        reasoning_effort: str | None = None,
        agentic_evidence: str | None = None,
        agentic_max_characters: int | None = None,
    ) -> str:
        if self.mock:
            return str(mock_reply(messages, json_mode=False))
        try:
            reasoning = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
            visual = bool(image_paths)
            request_messages = self._with_images(messages, image_paths) if visual else messages
            if agentic_evidence is not None and os.getenv("DEEPTUTOR_AGENTIC_ENABLED", "0") == "1":
                if os.getenv("DEEPTUTOR_LLM_ENABLED", "0") != "1":
                    raise LLMError("教学执行链需要先启用 DeepTutor 模型网关")
                from integrations.deeptutor.client import DeepTutorBackend
                content, reason = DeepTutorBackend().generate(request_messages,
                    model=self.vision_model if visual else self.model, temperature=temperature,
                    max_tokens=max_tokens, timeout=timeout, reasoning_effort=reasoning_effort,
                    evidence=agentic_evidence, max_characters=agentic_max_characters)
                if reason != "stop" or not content.strip():
                    raise LLMError("教学执行链未完成回答")
                return content.strip()
            content, reason = (
                self._one_call(request_messages, temperature, max_tokens, self.vision_model, timeout=timeout, **reasoning)
                if visual else self._one_call(request_messages, temperature, max_tokens, timeout=timeout, **reasoning)
            )
            if not content and reason == "length" and timeout is None:
                retry_tokens = max(max_tokens * 2, 1200)
                content, reason = (
                    self._one_call(request_messages, temperature, retry_tokens, self.vision_model, timeout=timeout, **reasoning)
                    if visual else self._one_call(request_messages, temperature, retry_tokens, timeout=timeout, **reasoning)
                )
            if reason == "length":
                raise LLMError("模型输出达到长度上限，未完成回答")
            if not content.strip():
                raise LLMError("模型输出达到长度上限，未完成回答" if reason == "length" else "模型未返回文本内容")
            return content.strip()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("模型调用失败：" + str(exc)) from exc

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        timeout: float | None = None,
        tool_choice: str | None = None,
        model: str | None = None,
    ) -> ChatToolResult:
        """One OpenAI-compatible tool-calling round.

        The loop owns orchestration; this method only sends the current
        messages/tools and returns a normalized assistant round. It does not
        execute tools and does not start an upstream application.
        """
        if self.mock:
            text = str(mock_reply(messages, json_mode=False))
            return ChatToolResult(text=text, finish_reason="stop")
        try:
            args: Dict[str, Any] = {
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if tools:
                args["tools"] = tools
                args["tool_choice"] = tool_choice or "auto"
            client = self._client_lazy()
            if timeout is not None:
                client = client.with_options(timeout=timeout, max_retries=0)
            response = client.chat.completions.create(**args)
            choice = response.choices[0]
            message = choice.message
            text = message.content or ""
            calls: list[ChatToolCall] = []
            for raw in getattr(message, "tool_calls", None) or []:
                function = getattr(raw, "function", None)
                if function is None:
                    continue
                raw_arguments = getattr(function, "arguments", "") or "{}"
                try:
                    parsed = extract_json(raw_arguments)
                except (ValueError, TypeError):
                    parsed = {}
                calls.append(ChatToolCall(
                    id=str(getattr(raw, "id", "") or f"call_{len(calls)}"),
                    name=str(getattr(function, "name", "") or ""),
                    arguments=parsed,
                    raw_arguments=str(raw_arguments),
                ))
            usage = {}
            raw_usage = getattr(response, "usage", None)
            if raw_usage is not None:
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    value = getattr(raw_usage, key, None)
                    if isinstance(value, int):
                        usage[key] = value
            return ChatToolResult(text=text, tool_calls=calls,
                                  finish_reason=str(choice.finish_reason or ""), usage=usage)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("模型调用失败：" + str(exc)) from exc

    def chat_json(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 2500,
        retries: int = 1,
        image_paths: Optional[List[Path]] = None,
        timeout: float | None = None,
        reasoning_effort: str | None = None,
    ) -> Dict[str, Any]:
        if self.mock:
            result = mock_reply(messages, json_mode=True)
            return dict(result) if isinstance(result, dict) else {}
        last_error: Exception | None = None
        for _ in range(retries + 1):
            try:
                return extract_json(self.chat(messages, temperature, max_tokens,
                                              image_paths=image_paths, timeout=timeout,
                                              **({"reasoning_effort": reasoning_effort} if reasoning_effort else {})))
            except (ValueError, LLMError) as exc:
                last_error = exc
        error_type = LLMJSONError if isinstance(last_error, ValueError) else LLMError
        raise error_type("无法获取有效 JSON：" + str(last_error))
