"""Host product allow-list for capabilities exposed through native chat."""
from __future__ import annotations

CHAT_CAPABILITIES = frozenset({
    "chat",
    "ask_questions",
    "mastery",
    "solve",
    "immersive_reading",
    "course_study",
    "explore_context",
    "visualization_generation",
    "deep_question",
})

HIDDEN_CAPABILITIES = frozenset({
    "obsidian",
    "marginnote4",
    "subagent",
    "ima",
    "setup",
    "partner_authoring",
    "partner_group",
})


def validate_options(options: dict) -> dict:
    capability = str(options.get("capability") or "chat")
    if capability not in CHAT_CAPABILITIES:
        raise ValueError("capability_not_enabled")
    if HIDDEN_CAPABILITIES.intersection(options.get("extensions") or ()):
        raise ValueError("extension_not_enabled")
    return options
