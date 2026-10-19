# Q4 tool foundation

This package follows the Q3 contract in
`docs/research/2026-10-19-deeptutor-conversation-flow/Q3_INTERFACE_CONTRACT.md`.
It does not run a loop. Q3 owns the loop, task identity, events, and
`agents/tool_dispatch.py`.

## Mount one turn

```python
from agents.tools import (
    Allowlist, ScopedToolRegistry, ToolContext, ToolGrant, ToolRegistry,
    dispatch_tool_calls,
)

base = ToolRegistry()
base.load_builtins()                    # lazy specs, not all implementations

grant = ToolGrant(
    tools=Allowlist.of({"workspace_read", "read_skill"}),
    scopes=frozenset({"workspace:read", "skills:read"}),
)
registry = ScopedToolRegistry(
    base=base,
    selected=["workspace_read", "read_skill"],
    grant=grant,
)

loader = DeferredToolLoader(
    registry=base,                 # broad catalogue containing deferred specs
    session_id="...",
    on_loaded=registry.mount_tool, # mount into this turn, not only append schema
)

context = ToolContext(
    student_id="...",
    session_id="...",
    task_id="...",
    request_id="...",
    state={
        "workspace_root": "/task/workspace",
        "skills_root": "/project/skills",
        "deferred_loader": loader,
    },
)
outcome = dispatch_tool_calls(
    tool_calls=model_tool_calls,       # Q3 normalized call rows
    registry=registry,
    context=context,
    max_calls=15,
    timeout_seconds=30,
)
```

`ScopedToolRegistry` only contains granted tools; an unmounted name is refused by
Q3's dispatcher and an `AuthorizationProxy` checks the grant again at `run`.
`load_tools` needs `context.state["deferred_loader"]`; the loader's `on_loaded`
callback mounts the tool into this turn and Q3 re-reads `registry.schemas()` each
round. Without a real MCP/CLI provider it remains a pending capability, not a
verified external integration.

## Files

| File | Purpose |
| --- | --- |
| `protocol.py` | Re-export Q3 protocol; contract-shaped fallback for the standalone Q4 worktree |
| `scope.py` | `Allowlist`, `ToolGrant`, `ToolScope` |
| `registry.py` | lazy catalogue, aliases, plugins, scoped/authorized view |
| `validation.py` | required/type/enum/unknown argument checks |
| `loader.py` | deferred manifest and same-turn schema loading |
| `mounting.py` | scene/context/extension tool composition |
| `extensions.py` | 14 extension activation gates and owned tools |
| `dispatch.py` | thin bridge to Q3 `tool_dispatch`; no duplicate dispatcher |
| `workspace_tools.py` | `workspace_list/read/search` (read-only) |
| `skill_tools.py` | `read_skill`, `load_tools` |

The 100-tool / 14-extension migration status is in
`Q4_TOOL_LEDGER.md`; it is not implied by this package's file list.
