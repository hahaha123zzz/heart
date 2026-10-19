"""Q4 tool foundation aligned with the Q3 tool contract."""

from agents.tools.dispatch import Q3DispatchUnavailable, dispatch_tool_calls
from agents.tools.extensions import (
    EXTENSIONS,
    ExtensionFlags,
    ExtensionSpec,
    active_extensions,
    owned_tools_for,
)
from agents.tools.loader import DeferredToolLoader, render_deferred_tools_manifest
from agents.tools.mounting import (
    ToolMountFlags,
    compose_enabled_tools,
    compose_for_scene,
    default_optional_tools,
)
from agents.tools.protocol import (
    PROTOCOL_SOURCE,
    BaseTool,
    ToolContext,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)
from agents.tools.registry import (
    AuthorizationProxy,
    ScopedToolRegistry,
    ToolRegistry,
    ToolSpec,
)
from agents.tools.scope import Allowlist, ToolGrant, ToolScope

__all__ = [
    "Allowlist",
    "AuthorizationProxy",
    "BaseTool",
    "DeferredToolLoader",
    "EXTENSIONS",
    "ExtensionFlags",
    "ExtensionSpec",
    "PROTOCOL_SOURCE",
    "Q3DispatchUnavailable",
    "ScopedToolRegistry",
    "ToolContext",
    "ToolDefinition",
    "ToolGrant",
    "ToolMountFlags",
    "ToolParameter",
    "ToolRegistry",
    "ToolResult",
    "ToolScope",
    "ToolSpec",
    "active_extensions",
    "compose_enabled_tools",
    "compose_for_scene",
    "default_optional_tools",
    "dispatch_tool_calls",
    "owned_tools_for",
    "render_deferred_tools_manifest",
]
