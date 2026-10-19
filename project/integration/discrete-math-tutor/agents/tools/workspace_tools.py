"""Read-only workspace tools over a task-owned directory.

These tools implement the Q3 protocol (``BaseTool.run(arguments, context)``).
The trusted task layer places ``workspace_root`` in ``ToolContext.state``; a
model-authored root is never accepted.  Every relative path is resolved and
re-checked against that root before any I/O.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agents.tools.protocol import BaseTool, ToolContext, ToolDefinition, ToolParameter, ToolResult

MAX_READ_CHARS = 100_000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_LIST_ENTRIES = 1_000
MAX_SEARCH_MATCHES = 200
MAX_SEARCH_FILES = 5_000
SKIP_DIRECTORIES = frozenset({".git", ".venv", "__pycache__", "node_modules"})


class WorkspaceAccessError(Exception):
    pass


def _root(context: ToolContext) -> Path:
    raw = context.state.get("workspace_root")
    if not raw:
        raise WorkspaceAccessError("No active workspace is bound to this task.")
    root = Path(str(raw)).resolve()
    if not root.is_dir():
        raise WorkspaceAccessError("The bound workspace is not a readable directory.")
    return root


def _resolve(root: Path, relative: str) -> Path:
    relative = str(relative or ".").strip()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise WorkspaceAccessError("Path escapes the active workspace.")
    return candidate


def _relative(root: Path, path: Path) -> str:
    return "." if path == root else path.relative_to(root).as_posix()


def _failure(exc: Exception) -> ToolResult:
    return ToolResult(
        content=str(exc),
        success=False,
        metadata={"error": "workspace_access", "detail": str(exc)},
    )


class WorkspaceListTool(BaseTool):
    definition = ToolDefinition(
        name="workspace_list",
        description=(
            "List files and folders in the task workspace using relative paths. "
            "Use this before claiming that a local file is unavailable."
        ),
        parameters=(
            ToolParameter(
                name="path",
                type="string",
                description="Workspace-relative directory; defaults to the root.",
                required=False,
            ),
            ToolParameter(
                name="depth",
                type="integer",
                description="Directory depth from 1 to 5.",
                required=False,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum entries, up to 1000.",
                required=False,
            ),
        ),
    )
    scopes = ("workspace:read",)
    read_only = True

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        context.check_cancelled()
        try:
            root = _root(context)
            target = _resolve(root, str(arguments.get("path") or "."))
            if not target.is_dir():
                raise WorkspaceAccessError("Path is not a directory.")
            depth = min(max(int(arguments.get("depth") or 1), 1), 5)
            limit = min(max(int(arguments.get("limit") or 200), 1), MAX_LIST_ENTRIES)
            page = _list_entries(root, target, depth, limit)
        except (WorkspaceAccessError, OSError, ValueError) as exc:
            return _failure(exc)
        return ToolResult(content=json.dumps(page, ensure_ascii=False, indent=2), metadata=page)


class WorkspaceReadTool(BaseTool):
    definition = ToolDefinition(
        name="workspace_read",
        description=(
            "Read a UTF-8 text file from the task workspace. Paths are relative "
            "to the workspace; use workspace_list or workspace_search first."
        ),
        parameters=(
            ToolParameter(name="path", type="string", description="Relative file path."),
            ToolParameter(
                name="offset",
                type="integer",
                description="Character offset for paginated reads.",
                required=False,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum characters to return, up to 100000.",
                required=False,
            ),
        ),
    )
    scopes = ("workspace:read",)
    read_only = True

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        context.check_cancelled()
        try:
            root = _root(context)
            target = _resolve(root, str(arguments.get("path") or ""))
            if not target.is_file():
                raise WorkspaceAccessError("Path is not a file.")
            offset = max(int(arguments.get("offset") or 0), 0)
            limit = min(max(int(arguments.get("limit") or 20_000), 1), MAX_READ_CHARS)
            if target.stat().st_size > MAX_FILE_BYTES:
                raise WorkspaceAccessError("File is too large to read as text.")
            text = target.read_text(encoding="utf-8")
            chunk = text[offset : offset + limit]
        except (WorkspaceAccessError, OSError, UnicodeDecodeError, ValueError) as exc:
            return _failure(exc)
        next_offset = offset + len(chunk)
        return ToolResult(
            content=chunk,
            metadata={
                "path": _relative(root, target),
                "char_count": len(text),
                "offset": offset,
                "next_offset": next_offset,
                "truncated": next_offset < len(text),
            },
        )


class WorkspaceSearchTool(BaseTool):
    definition = ToolDefinition(
        name="workspace_search",
        description="Search filenames and UTF-8 text inside the task workspace.",
        parameters=(
            ToolParameter(name="query", type="string", description="Text to find."),
            ToolParameter(
                name="path",
                type="string",
                description="Relative directory to search; defaults to the root.",
                required=False,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum matches, up to 200.",
                required=False,
            ),
        ),
    )
    scopes = ("workspace:read",)
    read_only = True

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        context.check_cancelled()
        try:
            root = _root(context)
            target = _resolve(root, str(arguments.get("path") or "."))
            if not target.is_dir():
                raise WorkspaceAccessError("Path is not a directory.")
            query = str(arguments.get("query") or "").strip()
            if not query:
                raise WorkspaceAccessError("Search query must not be empty.")
            limit = min(max(int(arguments.get("limit") or 50), 1), MAX_SEARCH_MATCHES)
            page = _search(root, target, query, limit)
        except (WorkspaceAccessError, OSError, ValueError) as exc:
            return _failure(exc)
        return ToolResult(content=json.dumps(page, ensure_ascii=False, indent=2), metadata=page)


def _list_entries(root: Path, target: Path, depth: int, limit: int) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    truncated = False

    def _walk(directory: Path, remaining: int) -> None:
        nonlocal truncated
        if remaining <= 0:
            truncated = True
            return
        rows = sorted(
            (row for row in os.scandir(directory) if row.name not in SKIP_DIRECTORIES),
            key=lambda row: (not row.is_dir(follow_symlinks=False), row.name.lower()),
        )
        for row in rows:
            if len(entries) >= limit:
                truncated = True
                return
            path = Path(row.path)
            item = {
                "path": _relative(root, path),
                "name": row.name,
                "type": "directory" if row.is_dir(follow_symlinks=False) else "file",
            }
            if item["type"] == "file":
                try:
                    item["size"] = row.stat(follow_symlinks=False).st_size
                except OSError:
                    item["size"] = None
            entries.append(item)
            if item["type"] == "directory" and remaining > 1:
                _walk(path, remaining - 1)

    _walk(target, depth)
    return {
        "path": _relative(root, target),
        "depth": depth,
        "entries": entries,
        "truncated": truncated,
        "count": len(entries),
    }


def _search(root: Path, target: Path, query: str, limit: int) -> dict[str, Any]:
    folded = query.casefold()
    matches: list[dict[str, Any]] = []
    scanned = 0
    truncated = False
    for directory, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRECTORIES)
        for filename in sorted(filenames):
            if len(matches) >= limit or scanned >= MAX_SEARCH_FILES:
                truncated = True
                break
            path = Path(directory) / filename
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                relative = _relative(root, path)
            except (OSError, ValueError):
                continue
            scanned += 1
            if folded in filename.casefold():
                matches.append(
                    {"path": relative, "kind": "filename", "line": None, "snippet": filename}
                )
                if len(matches) >= limit:
                    truncated = True
                    break
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if folded not in line.casefold():
                    continue
                matches.append(
                    {
                        "path": relative,
                        "kind": "content",
                        "line": line_number,
                        "snippet": line.strip()[:240],
                    }
                )
                if len(matches) >= limit:
                    truncated = True
                    break
            if len(matches) >= limit:
                break
        if len(matches) >= limit or scanned >= MAX_SEARCH_FILES:
            break
    return {
        "query": query,
        "path": _relative(root, target),
        "matches": matches,
        "count": len(matches),
        "truncated": truncated,
        "files_scanned": scanned,
    }


__all__ = [
    "WorkspaceAccessError",
    "WorkspaceListTool",
    "WorkspaceReadTool",
    "WorkspaceSearchTool",
]
