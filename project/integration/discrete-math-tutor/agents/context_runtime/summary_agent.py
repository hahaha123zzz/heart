"""上游摘要构建器的模型边界：沿用宿主网关、预算和错误处理。"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar

summary_client = ContextVar("context_summary_client", default=None)


class ContextSummaryAgent:
    def __init__(self, language="zh"):
        self.language = language
        self.trace_callback = None

    def set_trace_callback(self, callback):
        self.trace_callback = callback

    async def stream_llm(self, *, user_prompt, system_prompt, max_tokens,
                         stage, trace_meta, messages=None, tools=None):
        from llm.client import LLMClient, LLMError
        from llm.execution_budget import stage_call
        client = summary_client.get() or LLMClient()
        messages = messages or [{"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}]
        async def trace(state, **kwargs):
            if self.trace_callback:
                await self.trace_callback({**trace_meta, "event": "llm_call", "state": state, **kwargs})
        def complete():
            if tools:
                result = client.chat_with_tools(messages, tools, temperature=0,
                    max_tokens=max_tokens, tool_choice="none", timeout=90)
                if result.tool_calls or result.finish_reason != "stop":
                    raise LLMError("上下文摘要未完整结束")
                return result.text
            return client.chat(messages, temperature=0, max_tokens=max_tokens, timeout=90)
        await trace("running")
        try:
            text = await asyncio.to_thread(stage_call, "context_summary", complete)
        except Exception:
            await trace("error", response="上下文摘要生成失败")
            raise
        await trace("complete", response=text)
        yield text
