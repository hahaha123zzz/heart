"""Per-scene tool composition.

Adapted from DeepTutor's ``agents/_shared/tool_composition.py``.  The rule is
kept deliberately conservative: a scene starts from its baseline, user toggles
and trusted context flags may add tools, and an extension's owned tools are
added only while that extension's activation gate is true.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agents.tools.extensions import ExtensionFlags, active_extensions, owned_tools_for

USER_TOGGLEABLE_TOOL_NAMES: tuple[str, ...] = (
    "brainstorm",
    "web_search",
    "paper_search",
    "zotero_search",
    "reason",
    "geogebra_analysis",
    "imagegen",
    "videogen",
)

# Tool name -> ToolMountFlags field.  Insertion order fixes the default order.
CONDITIONAL_MOUNT_FLAGS: tuple[tuple[str, str], ...] = (
    ("preprint", "has_scientific_research"),
    ("research_audit", "has_scientific_research"),
    ("research_lit", "has_scientific_research"),
    ("rag", "has_kb"),
    ("kb_files", "has_kb"),
    ("knowledge_frontier", "has_kb"),
    ("read_source", "has_sources"),
    ("read_memory", "has_memory"),
    ("list_notebook", "has_notebooks"),
    ("write_note", "has_notebooks"),
    ("question_bank", "has_question_bank"),
    ("read_skill", "has_skills"),
    ("load_tools", "has_deferred_tools"),
    ("exec", "has_exec"),
    ("mastery_topics", "has_mastery_topics"),
    ("mastery_sessions", "has_mastery_nav"),
    ("mastery_open_session", "has_mastery_nav"),
    ("mastery_new_session", "has_mastery_nav"),
)

ALWAYS_ON_TOOL_NAMES: tuple[str, ...] = (
    "write_memory",
    "learning_status",
    "learning_update",
    "web_fetch",
    "github",
    "ask_user",
    "cron",
)

WORKSPACE_BASELINE_TOOLS: tuple[str, ...] = (
    "workspace_list",
    "workspace_read",
    "workspace_search",
)

AUTO_MOUNTED_TOOLS: frozenset[str] = frozenset(
    {name for name, _flag in CONDITIONAL_MOUNT_FLAGS} | set(ALWAYS_ON_TOOL_NAMES)
)

SCENE_BASELINE_TOOLS: dict[str, tuple[str, ...]] = {
    "chat": WORKSPACE_BASELINE_TOOLS,
    "ask_questions": (*WORKSPACE_BASELINE_TOOLS, "ask_user"),
    "deep_solve": WORKSPACE_BASELINE_TOOLS,
    "deep_question": WORKSPACE_BASELINE_TOOLS,
    "deep_research": WORKSPACE_BASELINE_TOOLS,
    "math_animator": WORKSPACE_BASELINE_TOOLS,
    "visualize": WORKSPACE_BASELINE_TOOLS,
    "mastery_path": WORKSPACE_BASELINE_TOOLS,
    "immersive_reading": WORKSPACE_BASELINE_TOOLS,
    "course_study": WORKSPACE_BASELINE_TOOLS,
    "audio_overview": WORKSPACE_BASELINE_TOOLS,
}


@dataclass(frozen=True, slots=True)
class ToolMountFlags:
    """Trusted per-turn facts that drive conditional mounting."""

    has_workspace: bool = True
    has_kb: bool = False
    has_sources: bool = False
    has_memory: bool = False
    has_notebooks: bool = False
    has_question_bank: bool = False
    has_skills: bool = False
    has_deferred_tools: bool = False
    has_scientific_research: bool = False
    has_exec: bool = False
    has_mastery_nav: bool = False
    has_mastery_topics: bool = False
    extension_flags: ExtensionFlags = field(default_factory=ExtensionFlags)


def default_optional_tools(excluded: Iterable[str] = ()) -> list[str]:
    excluded_set = frozenset(excluded)
    return [
        name
        for name in USER_TOGGLEABLE_TOOL_NAMES
        if name not in excluded_set and name not in AUTO_MOUNTED_TOOLS
    ]


def compose_enabled_tools(
    *,
    registry: Any,
    requested_tools: Iterable[str] = (),
    optional_whitelist: Iterable[str] | None = None,
    mount_flags: ToolMountFlags | None = None,
    capability_owned: Iterable[str] = (),
    forced: Iterable[str] = (),
    suppressed: Iterable[str] = (),
    exclusive: bool = False,
) -> list[str]:
    """Return the ordered, available, de-duplicated tool list for one turn."""

    flags = mount_flags or ToolMountFlags()
    available = {tool.definition.name for tool in _enabled(registry, _all_names(registry))}
    optional = set(optional_whitelist) if optional_whitelist is not None else None

    def _available(name: str) -> bool:
        return name in available

    def _optional(name: str) -> bool:
        return optional is None or name in optional

    if exclusive:
        names = [
            *WORKSPACE_BASELINE_TOOLS,
            *capability_owned,
            *(name for name in ("rag", "kb_files", "knowledge_frontier") if flags.has_kb),
            "ask_user",
        ]
        return _finalize(names, forced, suppressed, _available)

    names: list[str] = []
    for tool in _enabled(registry, requested_tools):
        if tool.definition.name in USER_TOGGLEABLE_TOOL_NAMES and _optional(tool.definition.name):
            names.append(tool.definition.name)
    for tool_name, flag_name in CONDITIONAL_MOUNT_FLAGS:
        if getattr(flags, flag_name, False):
            names.append(tool_name)
    names.extend(str(name) for name in capability_owned if str(name).strip())
    for tool_name in ALWAYS_ON_TOOL_NAMES:
        names.append(tool_name)
    if flags.has_workspace:
        names = [*WORKSPACE_BASELINE_TOOLS, *names]
    return _finalize(names, forced, suppressed, _available)


def compose_for_scene(
    *,
    scene: str,
    registry: Any,
    mount_flags: ToolMountFlags | None = None,
    requested_tools: Iterable[str] = (),
    optional_whitelist: Iterable[str] | None = None,
    forced: Iterable[str] = (),
    suppressed: Iterable[str] = (),
) -> list[str]:
    """Compose a scene using its baseline plus active-extension owned tools."""

    flags = mount_flags or ToolMountFlags()
    normalized = str(scene or "chat").strip().lower()
    active = active_extensions(flags.extension_flags, normalized)
    owned = owned_tools_for(active)
    baseline = SCENE_BASELINE_TOOLS.get(normalized, WORKSPACE_BASELINE_TOOLS)
    composed = compose_enabled_tools(
        registry=registry,
        requested_tools=requested_tools,
        optional_whitelist=optional_whitelist,
        mount_flags=flags,
        capability_owned=owned,
        forced=forced,
        suppressed=suppressed,
    )
    # Keep the scene baseline first, then the composed surface.  The final
    # filter drops tools that the registry cannot actually provide.
    available = {tool.definition.name for tool in _enabled(registry, _all_names(registry))}
    return _finalize([*baseline, *composed], (), (), lambda name: name in available)


def _all_names(registry: Any) -> list[str]:
    names = getattr(registry, "names", None)
    if callable(names):
        return list(names())
    return list(registry.list_tools())


def _enabled(registry: Any, names: Iterable[str]) -> list[Any]:
    getter = getattr(registry, "get_enabled", None)
    if callable(getter):
        return list(getter(list(names)))
    return [tool for tool in (registry.get(name) for name in names) if tool is not None]


def _finalize(
    names: Iterable[str],
    forced: Iterable[str],
    suppressed: Iterable[str],
    available,
) -> list[str]:
    all_names = [*names, *forced]
    suppressed_set = {str(name) for name in suppressed}
    seen: set[str] = set()
    out: list[str] = []
    for name in all_names:
        name = str(name)
        if not name or name in seen or name in suppressed_set or not available(name):
            continue
        seen.add(name)
        out.append(name)
    return out


__all__ = [
    "ALWAYS_ON_TOOL_NAMES",
    "AUTO_MOUNTED_TOOLS",
    "CONDITIONAL_MOUNT_FLAGS",
    "SCENE_BASELINE_TOOLS",
    "ToolMountFlags",
    "USER_TOGGLEABLE_TOOL_NAMES",
    "WORKSPACE_BASELINE_TOOLS",
    "compose_enabled_tools",
    "compose_for_scene",
    "default_optional_tools",
]
