"""Shared language directives for prompt-driven model calls.

Ported from DeepTutor ``deeptutor/services/prompt/language.py`` at the
vendored source revision recorded in LOCAL_MIGRATION_MAP.md. The module is
kept dependency-free so project prompts can share one language contract.
"""

from __future__ import annotations

_LANGUAGE_LABELS: dict[str, str] = {
    "zh": "中文（简体）",
    "zh-cn": "中文（简体）",
    "zh-tw": "繁體中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "ru": "Русский",
    "uk": "Українська",
    "pt": "Português",
    "it": "Italiano",
    "ar": "العربية",
    "pl": "Polski",
    "ms": "Bahasa Melayu",
}


def normalize_language(language: str | None) -> str:
    return (language or "en").strip().lower() or "en"


def is_chinese(language: str | None) -> bool:
    """Whether reader-facing text for *language* should be written in Chinese."""

    return normalize_language(language).startswith("zh")


def language_label(language: str | None) -> str:
    code = normalize_language(language)
    if code in _LANGUAGE_LABELS:
        return _LANGUAGE_LABELS[code]
    base = code.split("-", 1)[0]
    return _LANGUAGE_LABELS.get(base, language or "English")


_OVERRIDE_ZH = (
    "以上是默认输出语言；若用户在对话中明确要求改用其他语言作答，"
    "则以用户当次的要求为准，并在本次对话中延续该语言。"
)
_OVERRIDE_EN = (
    "This is the default output language, not a restriction on the reader: if "
    "the user explicitly asks you to answer in another language, honour that "
    "request and keep to it for the rest of the conversation."
)


def language_directive(language: str | None, *, allow_user_override: bool = False) -> str:
    """Return a reader-facing language instruction for prompts."""

    code = normalize_language(language)
    label = language_label(code)
    if code.startswith("zh"):
        body = (
            "\n\n[语言要求 / Language] "
            f"请严格使用{label}撰写所有面向读者的文本（标题、正文、解释、提示、过渡句、"
            "题干、选项等），即使参考资料、JSON 字段名或英文术语出现在 prompt 中也"
            "不得切换语言；保留必要的专有名词原文（如人名、产品名、公式中的变量符号"
            f"等）即可，其余一律使用{label}。"
        )
        return f"{body} {_OVERRIDE_ZH}" if allow_user_override else body
    if code == "en":
        body = (
            "\n\n[Language] Write ALL reader-facing text (titles, prose, "
            "explanations, hints, transitions, quiz stems, options, etc.) in "
            "English. Do NOT switch languages even if the source material, "
            "JSON keys, or examples in this prompt are in another language. "
            "Keep proper nouns (people, products, formula symbols) in their "
            "original form."
        )
        return f"{body} {_OVERRIDE_EN}" if allow_user_override else body
    body = (
        f"\n\n[Language] Write ALL reader-facing text strictly in {label}. "
        "Do NOT switch languages even if the source material, JSON keys, or "
        "examples in this prompt are in a different language. Keep proper "
        "nouns (people, products, formula symbols) in their original form."
    )
    return f"{body} {_OVERRIDE_EN}" if allow_user_override else body


def append_language_directive(
    system_prompt: str | None,
    language: str | None,
    *,
    allow_user_override: bool = False,
) -> str:
    """Append the language directive to an existing system prompt."""

    base = (system_prompt or "").rstrip()
    directive = language_directive(language, allow_user_override=allow_user_override).strip()
    if not base:
        return directive
    return f"{base}\n\n{directive}"


__all__ = [
    "append_language_directive",
    "is_chinese",
    "language_directive",
    "language_label",
    "normalize_language",
]
