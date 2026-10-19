"""复用上游隔离 Provider；不接收密钥、远程图片或任意工具请求。"""
import asyncio
import base64
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .session_bridge import require_bridge_token


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    messages: list[dict] = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(default=.4, ge=0, le=2)
    max_tokens: int = Field(default=1200, ge=1, le=16000)
    timeout: float = Field(default=120, ge=1, le=180)
    reasoning_effort: Literal["low", "high", "max"] | None = None

    @model_validator(mode="after")
    def trusted_messages(self):
        images = 0
        text_size = 0
        for message in self.messages:
            if (set(message) != {"role", "content"} or not isinstance(message["role"], str)
                    or message["role"] not in {"system", "user", "assistant"}):
                raise ValueError("消息角色或字段无效")
            content = message["content"]
            if isinstance(content, str):
                text_size += len(content)
                continue
            if not isinstance(content, list) or not 1 <= len(content) <= 3:
                raise ValueError("多模态消息无效")
            for part in content:
                if not isinstance(part, dict): raise ValueError("消息片段无效")
                if part.get("type") == "text" and set(part) == {"type", "text"} and isinstance(part["text"], str):
                    text_size += len(part["text"])
                elif part.get("type") == "image_url" and set(part) == {"type", "image_url"}:
                    value = part["image_url"]
                    if not isinstance(value, dict) or set(value) - {"url", "detail"}:
                        raise ValueError("图片字段无效")
                    url = value.get("url", "")
                    prefix = "data:image/png;base64,"
                    if not isinstance(url, str) or not url.startswith(prefix) or len(url) > 12 * 1024 * 1024:
                        raise ValueError("仅接受已审核教材的内嵌 PNG")
                    try:
                        data = base64.b64decode(url[len(prefix):], validate=True)
                    except ValueError as exc:
                        raise ValueError("图片编码无效") from exc
                    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8 * 1024 * 1024:
                        raise ValueError("图片格式或大小无效")
                    if value.get("detail", "original") not in {"original", "high", "low", "auto"}:
                        raise ValueError("图片精度无效")
                    images += 1
                else:
                    raise ValueError("消息片段无效")
        if images > 2 or text_size > 500000:
            raise ValueError("生成输入超过限制")
        return self


async def generate(request: GenerationRequest):
    from deeptutor.services.llm.config import LLMConfig
    from deeptutor.services.llm.provider_factory import build_isolated_provider
    from deeptutor.services.llm.utils import clean_thinking_tags

    text_model = os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL", "deepseek-flash")
    vision_model = os.getenv("OPENAI_VISION_MODEL", "deepseek-flash")
    if request.model not in {text_model, vision_model}:
        raise HTTPException(422, "模型不属于宿主配置")
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise HTTPException(503, "宿主模型尚未配置")
    config = LLMConfig(model=request.model, api_key=key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
        binding="openai", provider_name="openai", wire_api="chat_completions",
        max_tokens=request.max_tokens, temperature=request.temperature, reasoning_effort=request.reasoning_effort)
    provider = None
    try:
        provider = build_isolated_provider(config)
        kwargs = {}
        if "api.deepseek.com" in (config.base_url or ""):
            kwargs["extra_body"] = {"thinking": {"type": "enabled" if request.reasoning_effort else "disabled"}}
        response = await asyncio.wait_for(provider.chat_with_retry(messages=request.messages,
            model=config.model, reasoning_effort=config.reasoning_effort,
            retry_delays=[], allow_image_fallback=False, **kwargs), timeout=request.timeout)
        if response.finish_reason not in {"stop", "length", "max_tokens", "max_output_tokens"} or response.tool_calls:
            raise HTTPException(502, "上游模型未正常完成文本回答")
        content = response.content or ""
        if content == response.reasoning_content: content = ""
        content = clean_thinking_tags(content).strip()
        reason = "length" if response.finish_reason != "stop" else "stop"
        return {"content": content, "finish_reason": reason}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "DeepTutor 模型调用失败") from exc
    finally:
        if provider is not None: await provider.aclose()


def install_generation_bridge(app):
    router = APIRouter(prefix="/internal/heart", dependencies=[Depends(require_bridge_token)])
    router.add_api_route("/generate", generate, methods=["POST"])
    app.include_router(router)
