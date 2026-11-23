"""使用完整的 DeepTutor ContextBuilder；仅适配宿主的同步调用与历史行。"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from copy import deepcopy
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

from agents.context_runtime.context_builder import (
    ContextBuilder, count_tokens, MAX_HISTORY_PLAN_TOKENS,
)
from agents.context_runtime.model_history import history_groups, model_turn
from agents.context_runtime.summary_agent import summary_client

estimate_tokens = count_tokens


class _HistoryStore:
    def __init__(self, rows):
        self.rows = rows
        self.session = {"compressed_summary": "", "summary_up_to_msg_id": 0}
        for row in reversed(rows):
            summary = (row.get("metadata") or {}).get("context_summary")
            if (isinstance(summary, dict) and isinstance(summary.get("compressed_summary"), str)
                    and type(summary.get("summary_up_to_msg_id")) is int):
                self.session.update(summary)
                break

    async def get_session(self, session_id):
        return self.session

    async def get_messages_for_context(self, session_id, *, leaf_message_id=None):
        return self.rows

    async def update_summary(self, session_id, summary, up_to_msg_id):
        self.session.update(compressed_summary=summary, summary_up_to_msg_id=up_to_msg_id)


class _HostContextBuilder(ContextBuilder):
    def __init__(self, store, budget, summarizer):
        super().__init__(store)
        self.budget = budget
        self.summarizer = summarizer
        self.older = []

    def _history_budget(self, llm_config):
        budget = self.budget if self.budget is not None else super()._history_budget(llm_config)
        # 最新完整回合不能丢弃，也不应再生成一份自身的重复摘要。
        if len(history_groups(self.store.rows)) <= 1:
            return max(budget, self._model_tokens(self.store.rows))
        return budget

    def _select_recent_messages(self, messages, recent_budget):
        self.older, recent = super()._select_recent_messages(messages, recent_budget)
        return self.older, recent

    async def _summarize(self, **kwargs):
        if self.summarizer is not None:
            return self.summarizer(deepcopy(self.older)), []
        return await super()._summarize(**kwargs)


@dataclass(frozen=True)
class HistoryBuild:
    history: list[dict[str, str]]
    summary: str
    token_count: int
    budget: int
    dropped_messages: int
    model_history: list[dict[str, Any]] = field(default_factory=list)
    previous_model_turn: dict[str, Any] | None = None
    summary_up_to_msg_id: int = 0


def resolve_history_budget(*, model="", context_window=None):
    config = SimpleNamespace(model=model or "deepseek-flash", context_window=context_window, max_tokens=None)
    return ContextBuilder(None)._history_budget(config)


def _rows(history):
    rows = []
    for row in history or ():
        if (not isinstance(row, dict) or row.get("role") not in ("user", "assistant", "system")
                or not isinstance(row.get("content"), str) or not row["content"].strip()):
            continue
        item = {"id": row.get("id", len(rows) + 1), "role": row["role"], "content": row["content"]}
        if isinstance(row.get("metadata"), dict):
            item["metadata"] = deepcopy(row["metadata"])
        # 旧记录只有显示文本：补全上游回合契约，让预算切分仍以完整问答为单位。
        if item["role"] == "assistant" and rows and rows[-1]["role"] == "user" and model_turn(item) is None:
            item.setdefault("metadata", {})["model_turn"] = {"version": 1, "messages": [
                {"role": "user", "content": rows[-1]["content"]},
                {"role": "assistant", "content": item["content"]}]}
        rows.append(item)
    return rows


def build_history(history, *, model="", context_window=None, budget_tokens=None,
                  summarizer: Callable | None = None, llm=None) -> HistoryBuild:
    if budget_tokens is not None and (type(budget_tokens) is not int or budget_tokens <= 0):
        raise ValueError("历史 token 预算必须为正整数")
    from llm.client import LLMClient, answer_max_tokens
    client = llm or LLMClient()
    store = _HistoryStore(_rows(history))
    builder = _HostContextBuilder(store, budget_tokens, summarizer)
    config = SimpleNamespace(model=model or client.model,
                             context_window=context_window, max_tokens=answer_max_tokens(), binding=None)
    def run():
        return asyncio.run(builder.build(session_id="host-history", llm_config=config, language="zh"))
    token = summary_client.set(client)
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = run()
        else:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="context-builder") as pool:
                result = pool.submit(copy_context().run, run).result()
    finally:
        summary_client.reset(token)
    display = [{"role": row["role"], "content": row["content"]}
               for row in result.conversation_history if row["role"] in ("user", "assistant")]
    return HistoryBuild(display, result.conversation_summary, result.token_count,
        budget_tokens if budget_tokens is not None else result.budget,
        max(0, len(store.rows) - len(display)), result.model_history or [], result.previous_model_turn,
        store.session["summary_up_to_msg_id"])


__all__ = ["HistoryBuild", "build_history", "estimate_tokens", "history_groups", "resolve_history_budget"]
