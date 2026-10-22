"""Bridge DeepTutor runtime configuration into the LightRAG 1.5 native SDK.

This module is the decoupling seam: it exposes availability + mode helpers and
builds the three adapters LightRAG needs from DeepTutor's already-resolved LLM,
vision, and embedding clients. LightRAG imports remain lazy so every other RAG
provider can import without the optional extra installed.

Decoupling notes:
* ``llm_model_func`` / ``vision_model_func`` wrap DeepTutor's unified model
  callables and DROP LightRAG's internal kwargs (``hashing_kv``,
  ``keyword_extraction``, …) so they never leak into ``factory.complete``.
* ``embedding_func`` reuses DeepTutor's embedding client, wrapped in LightRAG's
  ``EmbeddingFunc`` with the active model's dimension.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
import importlib.util
import inspect
import logging
import re
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from lightrag.utils import EmbeddingFunc


    from .worker import OwnerLoopBridge

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# LightRAG's native retrieval modes. ``hybrid`` (KG + vector) is the safest
# general default and matches the shared per-KB ``search_mode`` default.
SUPPORTED_MODES = ("naive", "local", "global", "hybrid", "mix")
DEFAULT_MODE = "hybrid"

# Conservative cap for the embedding wrapper when the model doesn't advertise one.
_DEFAULT_MAX_TOKEN_SIZE = 8192

# Keep retries at the LightRAG adapter boundary so the SDK receives one
# predictable policy for both text and vision calls. Provider retries are disabled
# on every attempt to prevent the two retry layers from multiplying.
_ADAPTER_MAX_ATTEMPTS = 3
_ADAPTER_RETRY_DELAYS_SECONDS = (1.0, 2.0)
_ADAPTER_MAX_RETRY_DELAY_SECONDS = 60.0
_RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504, 529})
_HTTP_STATUS_PATTERN = re.compile(
    r"\b(?:http(?: status)?|status(?: code)?|error code)\s*[:=-]?\s*(\d{3})\b",
    re.I,
)


class LightRagNotAvailableError(RuntimeError):
    """Raised when the optional ``lightrag-hku`` dependency is not installed."""


class LightRagNotConfiguredError(RuntimeError):
    """Raised when DeepTutor's LLM / embedding config can't back LightRAG."""


def _http_status_code(exc: Exception) -> int | None:
    """Return a structured or safely normalized HTTP status for an LLM error."""
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        return status_code

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int) and not isinstance(response_status, bool):
        return response_status

    # The Codex provider currently returns a safe, normalized ``HTTP NNN``
    # message through LLMAPIError instead of preserving the status attribute.
    is_llm_api_error = any(cls.__name__ == "LLMAPIError" for cls in type(exc).__mro__)
    message = getattr(exc, "message", None)
    if is_llm_api_error and isinstance(message, str):
        match = _HTTP_STATUS_PATTERN.search(message)
        if match is not None:
            return int(match.group(1))
    return None


def _retry_classification(exc: Exception) -> tuple[bool, str]:
    """Classify retryability without inspecting or logging provider payloads."""
    from httpx import TransportError
    from openai import APIConnectionError,APITimeoutError
    def is_transient_transport_error(error):
        return isinstance(error, (TransportError, TimeoutError, ConnectionError,APIConnectionError,APITimeoutError))

    status_code = _http_status_code(exc)
    if status_code is not None:
        return status_code in _RETRYABLE_HTTP_STATUS_CODES, f"http_{status_code}"
    if is_transient_transport_error(exc):
        return True, "transport"
    return False, "non_retryable"


def _retry_delay_seconds(exc: Exception, scheduled_delay: float) -> float:
    """Honor a safe Retry-After value without allowing unbounded sleeps."""
    def retry_after_seconds(error):
        try: return max(0.0, float(error.response.headers.get("retry-after")))
        except (AttributeError, TypeError, ValueError): return None

    requested_delay = retry_after_seconds(exc)
    if requested_delay is None:
        return scheduled_delay
    return min(requested_delay, _ADAPTER_MAX_RETRY_DELAY_SECONDS)


async def _run_adapter_with_retry(
    request: Callable[[], Awaitable[_T]],
    *,
    io_bridge: OwnerLoopBridge | None,
) -> _T:
    """Run one adapter request with bounded, non-multiplying retries."""
    for attempt in range(1, _ADAPTER_MAX_ATTEMPTS + 1):
        try:
            if io_bridge is not None:
                return await io_bridge.run(request)
            return await request()
        except Exception as exc:
            should_retry, status = _retry_classification(exc)
            if not should_retry or attempt == _ADAPTER_MAX_ATTEMPTS:
                raise
            logger.warning(
                "LightRAG adapter retry attempt=%d exception=%s status=%s",
                attempt,
                type(exc).__name__,
                status,
            )
            delay = _retry_delay_seconds(exc, _ADAPTER_RETRY_DELAYS_SECONDS[attempt - 1])
            await asyncio.sleep(delay)

    raise AssertionError("unreachable")


def is_lightrag_available() -> bool:
    """True when the native LightRAG SDK can be imported.

    Opt-in extra: ``pip install 'deeptutor[rag-lightrag]'``. Until installed the
    provider is hidden / blocked in the UI.
    """
    return importlib.util.find_spec("lightrag") is not None


def normalize_mode(mode: str | None) -> str:
    """Coerce a stored ``search_mode`` to a valid LightRAG query mode.

    The per-KB ``search_mode`` field is shared across engines; anything that
    isn't a LightRAG mode falls back to :data:`DEFAULT_MODE`.
    """
    candidate = (mode or "").strip().lower()
    return candidate if candidate in SUPPORTED_MODES else DEFAULT_MODE



# 以下为宿主配置适配；不加载 DeepTutor 全局账户或模型目录。
import os
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from llm.client import LLMClient
from .file_io import atomic_write_json

@dataclass
class Metrics:
    path: Path | None = None
    calls: list = field(default_factory=list)
    limiter: Any = field(default=None, repr=False)
    embedding_batches: int = 0
    embedding_texts: int = 0
    lock: Any = field(default_factory=threading.Lock, repr=False)

    def record(self, item):
        with self.lock:
            self.calls.append(item)
            self.flush()

    def flush(self):
        if self.path:
            atomic_write_json(self.path, self.public())

    def public(self):
        return {"calls": list(self.calls), "llm_calls": len(self.calls),
                "usage": {key: sum(c.get("usage", {}).get(key, 0) or 0 for c in self.calls)
                          for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
                "embedding_batches": self.embedding_batches, "embedding_texts": self.embedding_texts,
                "cost": None, "cost_note": "服务未返回金额，未估算费用"}

@dataclass
class HostModel:
    client: Any
    metrics: Metrics
    role: str = "query"
    binding: str = "host-llm-client"

    @property
    def model(self): return self.client.model

    @property
    def thinking_mode(self):
        return "disabled" if self.model=="deepseek-flash" or "api.deepseek.com" in self.client.base_url else "provider_default"

    @property
    def identity(self):
        from .indexing_policy import _endpoint_identity
        return {"binding": self.binding, "model": self.model,
                "endpoint": _endpoint_identity(self.client.base_url), "role": self.role,
                "thinking":self.thinking_mode,"max_output_tokens":8192,"temperature":0.1}

@dataclass
class HostEmbedding:
    model: str = "BAAI/bge-small-zh-v1.5"
    dim: int = 512
    max_tokens: int = 512
    device: str = "cpu"
    metrics: Any = None
    weights_sha256: str = ""

    def signature(self):
        from .indexing_policy import _fingerprint
        return _fingerprint({"model": self.model, "dim": self.dim, "max_tokens": self.max_tokens,
                             "weights_sha256": self.weights_sha256})

def query_kwargs_from_settings():
    # 固定SDK先分配图谱摘要预算；显式留出原文空间，避免成功返回却0个教材块。
    return {"top_k": 20, "chunk_top_k": 12, "max_entity_tokens": 2000,
            "max_relation_tokens": 2000, "max_total_tokens": 10000, "enable_rerank": False}

def indexing_kwargs_from_settings(): return {"max_parallel_parse_native": 1}

def constructor_kwargs_from_settings():
    return {"llm_model_max_async": 2, "embedding_func_max_async": 1,
            "max_parallel_insert": 1, "max_parallel_analyze": 1, "entity_extract_max_gleaning": 0,
            "default_llm_timeout": 180, "chunk_token_size": 1200,
            "chunk_overlap_token_size": 100, "addon_params": {"language": "Chinese"}}

def build_llm_model_func(*, io_bridge=None, llm_config=None, owner=None):
    config = llm_config or HostModel(LLMClient(), Metrics())
    async def llm_model_func(prompt="", system_prompt=None, history_messages=None, messages=None,
                             response_format=None, enable_cot=False, **ignored):
        from openai import AsyncOpenAI
        if config.client.mock or not config.client.api_key:
            raise LightRagNotConfiguredError("真实建图需要已配置的本项目模型，禁止 mock")
        if os.getenv("DEEPTUTOR_LLM_ENABLED", "0") == "1":
            raise LightRagNotConfiguredError("LightRAG 不能通过完整 DeepTutor 应用调用模型")
        request_messages = list(messages) if messages else (
            ([{"role": "system", "content": system_prompt}] if system_prompt else [])
            + list(history_messages or []) + [{"role": "user", "content": prompt or ""}])
        kwargs = {}
        if response_format is not None:
            if hasattr(response_format, "model_json_schema"):
                request_messages.append({"role": "user", "content": "Return JSON conforming to: "
                                          + __import__("json").dumps(response_format.model_json_schema())})
                kwargs["response_format"] = {"type": "json_object"}
            elif isinstance(response_format, dict): kwargs["response_format"] = response_format
            else: raise ValueError("不支持的结构化输出契约")
        if config.thinking_mode=="disabled":
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        async def request():
            if config.metrics.limiter is None: config.metrics.limiter=asyncio.Semaphore(2)
            async with config.metrics.limiter:
                return await request_owned()
        async def request_owned():
            started=time.monotonic()
            from .indexing_policy import _endpoint_identity
            item={"role": config.role, "model": config.model, "status": "failed",
                  "endpoint":_endpoint_identity(config.client.base_url)}
            try:
                async with AsyncOpenAI(api_key=config.client.api_key, base_url=config.client.base_url,
                                       timeout=150, max_retries=0) as client:
                    response=await client.chat.completions.create(model=config.model,
                        messages=request_messages, temperature=0.1, max_tokens=8192, **kwargs)
                choice=response.choices[0]
                item.update(response_model=getattr(response,"model",None),finish_reason=choice.finish_reason,
                            usage=response.usage.model_dump() if response.usage else {})
                if choice.finish_reason == "length": raise RuntimeError("LightRAG 模型输出截断")
                content=choice.message.content
                if not content or not content.strip(): raise RuntimeError("LightRAG 模型返回空内容")
                item["status"]="success"
                return content
            except BaseException as exc:
                item["error_type"]=type(exc).__name__
                chain=[];cause=exc.__cause__
                while cause is not None and len(chain)<4:
                    chain.append({'type':type(cause).__name__,'message':str(cause).replace(config.client.api_key,'[REDACTED]')[:300]})
                    cause=cause.__cause__
                item['error_chain']=chain
                raise
            finally:
                item["seconds"]=time.monotonic()-started
                config.metrics.record(item)
        return await _run_adapter_with_retry(request, io_bridge=io_bridge)
    return llm_model_func

def build_vision_model_func(*, io_bridge=None, llm_config=None, owner=None):
    base=build_llm_model_func(io_bridge=io_bridge, llm_config=llm_config, owner=owner)
    async def vision(prompt="", system_prompt=None, history_messages=None, image_inputs=None,
                     messages=None, response_format=None, **ignored):
        if not isinstance(image_inputs,list) or len(image_inputs)!=1 or not isinstance(image_inputs[0],dict):
            raise ValueError("LightRAG vision requests must contain exactly one image input")
        payload=image_inputs[0]; value=payload.get("base64")
        if not isinstance(value,str) or not value.strip(): raise ValueError("图像 base64 为空")
        # SDK 可能给 data URI；保持真实 MIME，禁止文字回退。
        uri=value if value.startswith("data:image/") else "data:"+str(payload.get("mime_type") or "image/png")+";base64,"+value
        msgs=([{"role":"system","content":system_prompt}] if system_prompt else [])+list(history_messages or [])
        msgs.append({"role":"user","content":[{"type":"text","text":prompt},
            {"type":"image_url","image_url":{"url":uri}}]})
        return await base(messages=msgs,response_format=response_format)
    return vision

def build_embedding_func(*, io_bridge=None, embedding_config=None):
    import numpy as np
    from lightrag.utils import EmbeddingFunc
    cfg=embedding_config or HostEmbedding()
    if cfg.dim <= 0: raise LightRagNotConfiguredError("嵌入维度无效")
    async def embed(texts, context=None, **ignored):
        from knowledge.hybrid_retrieval import _embedder_on_device
        def run():
            model=_embedder_on_device(cfg.model,cfg.device)
            vectors=np.asarray(list(model.embed(texts)),dtype=np.float32)
            if vectors.shape!=(len(texts),cfg.dim) or not np.isfinite(vectors).all() or (np.linalg.norm(vectors,axis=1)==0).any():
                raise ValueError("嵌入维度/数值不符合索引契约")
            return vectors
        # 等待本地推理回调结束后才确认取消，防止取消后仍写用量。
        task=asyncio.create_task(asyncio.to_thread(run))
        try: vectors=await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        if cfg.metrics:
            with cfg.metrics.lock:
                cfg.metrics.embedding_batches+=1;cfg.metrics.embedding_texts+=len(texts);cfg.metrics.flush()
        return vectors
    return EmbeddingFunc(embedding_dim=cfg.dim,max_token_size=cfg.max_tokens,func=embed)
