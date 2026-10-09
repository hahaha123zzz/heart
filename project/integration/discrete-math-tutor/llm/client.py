"""Single OpenAI-compatible model gateway for the discrete-math tutor."""

from __future__ import annotations

import json
import os
import re
import base64
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

    def _client_lazy(self):
        if self._client is None:
            if not self.api_key:
                raise LLMError("缺少 DeepSeek API Key；设置 DEEPSEEK_API_KEY，或使用 LLM_MOCK=1。")
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def _one_call(
        self, messages: List[Dict[str, Any]], temperature: float, max_tokens: int,
        model: str | None = None,
    ) -> tuple[str, str | None]:
        args: dict[str, Any] = {
            "model": model or self.model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if "api.deepseek.com" in self.base_url:
            args["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self._client_lazy().chat.completions.create(**args)
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
            data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
            parts.append({"type": "image_url", "image_url": {"url": data_url, "detail": "original"}})
        result[-1]["content"] = parts
        return result

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.4,
        max_tokens: int = 1200,
        image_paths: Optional[List[Path]] = None,
    ) -> str:
        if self.mock:
            return str(mock_reply(messages, json_mode=False))
        try:
            visual = bool(image_paths)
            request_messages = self._with_images(messages, image_paths) if visual else messages
            content, reason = (
                self._one_call(request_messages, temperature, max_tokens, self.vision_model)
                if visual else self._one_call(request_messages, temperature, max_tokens)
            )
            if not content and reason == "length":
                retry_tokens = max(max_tokens * 2, 1200)
                content, _ = (
                    self._one_call(request_messages, temperature, retry_tokens, self.vision_model)
                    if visual else self._one_call(request_messages, temperature, retry_tokens)
                )
            if not content.strip():
                raise LLMError("模型未返回文本内容")
            return content.strip()
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
    ) -> Dict[str, Any]:
        if self.mock:
            result = mock_reply(messages, json_mode=True)
            return dict(result) if isinstance(result, dict) else {}
        last_error: Exception | None = None
        for _ in range(retries + 1):
            try:
                return extract_json(self.chat(messages, temperature, max_tokens,
                                              image_paths=image_paths))
            except (ValueError, LLMError) as exc:
                last_error = exc
        raise LLMError("无法获取有效 JSON：" + str(last_error))
