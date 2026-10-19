"""ask_user payloads and same-task answer substitution.

Adapted from DeepTutor ``deeptutor/tools/ask_user.py``. The card schema is
kept identical so existing/upstream frontend components can consume it; the
project's task repository owns persistence and revision checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_QUESTIONS = 4
MAX_OPTIONS = 8
MAX_OPTION_CHARS = 120
MAX_OPTION_DESC_CHARS = 200
MAX_HEADER_CHARS = 16
MAX_QUESTION_CHARS = 800
MAX_INTRO_CHARS = 400
MAX_PLACEHOLDER_CHARS = 120
_REDUNDANT_OTHER_LABELS = frozenset({"other", "其他", "其它"})


@dataclass(frozen=True)
class AskUserOption:
    label: str
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "description": self.description}


@dataclass(frozen=True)
class AskUserQuestion:
    id: str
    prompt: str
    options: tuple[AskUserOption, ...] = ()
    header: str | None = None
    multi_select: bool = False
    allow_free_text: bool = True
    placeholder: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "header": self.header,
            "multi_select": self.multi_select,
            "options": [option.to_dict() for option in self.options],
            "allow_free_text": self.allow_free_text,
            "placeholder": self.placeholder,
        }


@dataclass(frozen=True)
class AskUserPayload:
    questions: tuple[AskUserQuestion, ...]
    intro: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"intro": self.intro, "questions": [q.to_dict() for q in self.questions]}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _option(raw: Any) -> AskUserOption | None:
    if isinstance(raw, dict):
        label = _text(raw.get("label"))
        description = _text(raw.get("description")) or None
    else:
        label, description = _text(raw), None
    if not label:
        return None
    return AskUserOption(label=label[:MAX_OPTION_CHARS],
                         description=description[:MAX_OPTION_DESC_CHARS] if description else None)


def _question(raw: Any, index: int, used_ids: set[str]) -> AskUserQuestion | str:
    if not isinstance(raw, dict):
        return f"Question #{index + 1}: must be an object."
    prompt = _text(raw.get("prompt"))
    if not prompt:
        return f"Question #{index + 1}: `prompt` is required."
    prompt = prompt[:MAX_QUESTION_CHARS]
    qid = _text(raw.get("id")) or f"q{index + 1}"
    while qid in used_ids:
        qid = f"{qid}_2"
    used_ids.add(qid)
    options = tuple(
        option for option in (_option(item) for item in (raw.get("options") or ()))
        if option is not None and option.label.casefold() not in _REDUNDANT_OTHER_LABELS
    )[:MAX_OPTIONS]
    header = _text(raw.get("header"))[:MAX_HEADER_CHARS] or None
    placeholder = _text(raw.get("placeholder"))[:MAX_PLACEHOLDER_CHARS] or None
    return AskUserQuestion(
        id=qid, prompt=prompt, options=options, header=header,
        multi_select=bool(raw.get("multi_select", raw.get("multiSelect", False))),
        allow_free_text=bool(raw.get("allow_free_text", True)),
        placeholder=placeholder,
    )


def build_ask_user_payload(*, questions: Any = None, intro: Any = None,
                           question: Any = None, options: Any = None) -> tuple[AskUserPayload | None, str | None]:
    """Validate the model arguments; return ``(payload, error)``."""
    if questions is None and question is not None:
        questions = [{"id": "q1", "prompt": question, "options": options or []}]
    if not isinstance(questions, (list, tuple)) or not questions:
        return None, "`questions` must contain at least one question."
    normalised: list[AskUserQuestion] = []
    used: set[str] = set()
    for index, raw in enumerate(questions[:MAX_QUESTIONS]):
        built = _question(raw, index, used)
        if isinstance(built, str):
            return None, built
        normalised.append(built)
    intro_text = _text(intro)[:MAX_INTRO_CHARS] or None
    return AskUserPayload(questions=tuple(normalised), intro=intro_text), None


def format_user_reply(payload: dict[str, Any] | None, reply_text: str,
                      answers: list[dict[str, Any]] | None = None) -> str:
    """Render the answer that is substituted into the paused tool message."""
    lines: list[str] = []
    answer_by_id = {str(item.get("questionId") or item.get("question_id")): _text(item.get("text"))
                    for item in answers or [] if isinstance(item, dict)}
    for question in (payload or {}).get("questions") or []:
        if not isinstance(question, dict):
            continue
        qid = str(question.get("id") or "")
        answer = answer_by_id.get(qid) or (reply_text if len((payload or {}).get("questions") or []) == 1 else "")
        if answer:
            lines.append(f"{question.get('prompt', qid)} -> {answer}")
    if not lines and _text(reply_text):
        lines.append(_text(reply_text))
    return "\n".join(lines)


def substitute_answer(tool_messages: list[dict[str, Any]], tool_call_id: str,
                      directive: str) -> bool:
    """Replace the paused tool result in-place; return whether it matched."""
    for message in tool_messages:
        if message.get("role") == "tool" and message.get("tool_call_id") == tool_call_id:
            message["content"] = directive
            return True
    return False


__all__ = [
    "AskUserOption", "AskUserPayload", "AskUserQuestion",
    "build_ask_user_payload", "format_user_reply", "substitute_answer",
    "MAX_OPTIONS", "MAX_QUESTIONS",
]
