"""Budgeted conversation history for the project's tutoring turns.

This is the local adaptation of DeepTutor's session ``ContextBuilder``:
whole turns are retained, older turns are folded into a bounded rolling
summary, and the newest turn is always kept. The project owns the storage,
so the builder consumes plain display rows instead of the upstream session
store and never starts the upstream application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agents.context_window import resolve_effective_context_window

# Ratio-only budgets are impractical for large windows; keep the upstream caps.
HISTORY_BUDGET_RATIO = 0.35
MAX_HISTORY_PLAN_TOKENS = 131_072
MIN_HISTORY_BUDGET = 256
MAX_SUMMARY_TOKENS = 900
SUMMARY_ENTRY_CHARS = 180
SUMMARY_HEADER = "[对话摘要]"
MAX_HISTORY_CONTENT_CHARS = 4000

_SUMMARY_ROLES = {"user": "用户", "assistant": "助教", "system": "背景"}


def estimate_tokens(text: str) -> int:
    """Estimate tokens with tiktoken when available, else a char heuristic."""

    if not text:
        return 0
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // 4)


def resolve_history_budget(*, model: str = "", context_window=None) -> int:
    model_text = model if isinstance(model, str) else ""
    window = resolve_effective_context_window(
        context_window=context_window, model=model_text or "deepseek-flash"
    )
    return min(max(MIN_HISTORY_BUDGET, int(window * HISTORY_BUDGET_RATIO)),
               MAX_HISTORY_PLAN_TOKENS)


def _normalize(history) -> list[dict[str, str]]:
    rows = []
    for row in history or ():
        if not isinstance(row, dict):
            continue
        role = row.get("role")
        content = row.get("content")
        if role not in ("user", "assistant", "system") or not isinstance(content, str):
            continue
        if not content.strip():
            continue
        rows.append({"role": role, "content": content[:MAX_HISTORY_CONTENT_CHARS]})
    return rows


def history_groups(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """Keep a user turn and its assistant answer together across cuts."""

    groups: list[list[dict[str, str]]] = []
    for row in rows:
        if (
            row["role"] == "assistant"
            and groups
            and groups[-1][-1]["role"] == "user"
            and len(groups[-1]) == 1
        ):
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def _fold(text: str) -> str:
    return " ".join(str(text).split())


def summarize_messages(
    messages: list[dict[str, str]], *, max_tokens: int = MAX_SUMMARY_TOKENS
) -> str:
    """Fold dropped turns into a bounded, source-preserving summary.

    The summary keeps the earliest user request and the most recent dropped
    turns because those carry the task goal and the immediately preceding
    explanation. It never invents facts and never promotes an assistant
    draft to a student fact.
    """

    if not messages:
        return ""
    lines: list[str] = [SUMMARY_HEADER]
    used = estimate_tokens(SUMMARY_HEADER)
    # Earliest first, then the newest dropped turns if the budget allows.
    ordered = messages[:6] + messages[-6:] if len(messages) > 12 else messages
    seen: set[tuple[str, str]] = set()
    omitted = 0
    for message in ordered:
        label = _SUMMARY_ROLES.get(message["role"], message["role"])
        content = _fold(message["content"])[:SUMMARY_ENTRY_CHARS]
        key = (label, content)
        if key in seen:
            continue
        seen.add(key)
        line = f"- {label}：{content}"
        cost = estimate_tokens(line)
        if used + cost > max_tokens:
            omitted += 1
            continue
        lines.append(line)
        used += cost
    if omitted:
        lines.append(f"- 另有 {omitted} 条较早记录已压缩。")
    return "\n".join(lines)


@dataclass(frozen=True)
class HistoryBuild:
    history: list[dict[str, str]]
    summary: str
    token_count: int
    budget: int
    dropped_messages: int


def build_history(
    history,
    *,
    model: str = "",
    context_window=None,
    budget_tokens: int | None = None,
    summarizer: Callable[[list[dict[str, str]]], str] | None = None,
) -> HistoryBuild:
    """Select whole recent turns within budget and summarize the rest."""

    rows = _normalize(history)
    budget = int(budget_tokens) if budget_tokens is not None else resolve_history_budget(
        model=model, context_window=context_window
    )
    total = sum(estimate_tokens(row["content"]) for row in rows)
    if total <= budget:
        return HistoryBuild(list(rows), "", total, budget, 0)

    groups = history_groups(rows)
    selected: list[dict[str, str]] = []
    selected_tokens = 0
    cutoff = len(groups)
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        group_tokens = sum(estimate_tokens(row["content"]) for row in group)
        if selected and selected_tokens + group_tokens > budget:
            break
        selected = group + selected
        selected_tokens += group_tokens
        cutoff = index
        if selected_tokens >= budget:
            break

    dropped = [row for group in groups[:cutoff] for row in group]
    summary = ""
    if dropped:
        summary = summarizer(dropped) if summarizer is not None else summarize_messages(dropped)
    return HistoryBuild(
        history=selected,
        summary=summary,
        token_count=selected_tokens + estimate_tokens(summary),
        budget=budget,
        dropped_messages=len(dropped),
    )


__all__ = [
    "HistoryBuild",
    "build_history",
    "estimate_tokens",
    "history_groups",
    "resolve_history_budget",
    "summarize_messages",
]
