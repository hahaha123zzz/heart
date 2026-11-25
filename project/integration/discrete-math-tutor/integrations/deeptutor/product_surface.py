"""Host product allow-list for capabilities exposed through native chat."""
from __future__ import annotations

CHAT_CAPABILITIES = frozenset({
    "chat",
    "ask_questions",
    "deep_question",
    "deep_solve",
    "deep_research",
    "visualize",
})

WORKSPACE_CAPABILITIES = frozenset({
    "mastery_path",
    "immersive_reading",
    "course_study",
})

ENABLED_CAPABILITIES = CHAT_CAPABILITIES | WORKSPACE_CAPABILITIES
ENABLED_SKILLS = frozenset({"docx"})
UNVERIFIED_TOOLS = frozenset({
    "web_search",
    "paper_search",
    "zotero_search",
    "preprint",
    "research_lit",
    "research_audit",
    "web_fetch",
    "github",
    "imagegen",
    "videogen",
    "geogebra_analysis",
    "consult_subagent",
    "load_tools",
    "knowledge_frontier",
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
RENDER_MODES = frozenset({"auto", "svg", "chartjs", "mermaid", "mindmap", "html"})


def validate_options(options: dict) -> dict:
    capability = str(options.get("capability") or "chat")
    if capability not in ENABLED_CAPABILITIES:
        raise ValueError("capability_not_enabled")
    if HIDDEN_CAPABILITIES.intersection(options.get("extensions") or ()):
        raise ValueError("extension_not_enabled")
    if set(options.get("tools") or ()) & UNVERIFIED_TOOLS:
        raise ValueError("tool_not_enabled")
    if set(options.get("skills") or ()) - ENABLED_SKILLS or options.get("mcp"):
        raise ValueError("extension_not_enabled")
    render_mode = options.get("config", {}).get("render_mode", "auto")
    if render_mode not in RENDER_MODES:
        raise ValueError("render_mode_not_enabled")
    return options
