"""Catalogue of tools migrated into the project so far."""

from __future__ import annotations

from agents.tools.registry import ToolSpec
from agents.tools.skill_tools import LoadToolsTool, ReadSkillTool
from agents.tools.workspace_tools import (
    WorkspaceListTool,
    WorkspaceReadTool,
    WorkspaceSearchTool,
)

LOCAL_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("workspace_list", lambda: WorkspaceListTool()),
    ToolSpec("workspace_read", lambda: WorkspaceReadTool()),
    ToolSpec("workspace_search", lambda: WorkspaceSearchTool()),
    ToolSpec("read_skill", lambda: ReadSkillTool()),
    ToolSpec("load_tools", lambda: LoadToolsTool()),
)

# Local aliases are deliberately few.  Upstream aliases are retained for
# future tool migrations, but resolving an alias never fabricates a tool.
TOOL_ALIASES: dict[str, tuple[str, dict[str, object]]] = {
    "ws_list": ("workspace_list", {}),
    "ws_read": ("workspace_read", {}),
    "ws_search": ("workspace_search", {}),
    "skill_read": ("read_skill", {}),
    "pdf": ("read_source", {}),
    "rag_hybrid": ("rag", {"mode": "hybrid"}),
    "rag_naive": ("rag", {"mode": "naive"}),
    "rag_search": ("rag", {}),
}

__all__ = ["LOCAL_TOOL_SPECS", "TOOL_ALIASES"]
