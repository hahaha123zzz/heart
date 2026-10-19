"""Local skill reading and deferred-tool loading tools (Q3 protocol)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agents.tools.loader import DeferredToolLoader
from agents.tools.protocol import BaseTool, ToolContext, ToolDefinition, ToolParameter, ToolResult

_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MAX_SKILL_CHARS = 100_000
_MAX_FILE_LIST = 50


class SkillAccessError(Exception):
    pass


def _root(context: ToolContext) -> Path:
    raw = context.state.get("skills_root")
    if not raw:
        raise SkillAccessError("No skill library is bound to this task.")
    root = Path(str(raw)).resolve()
    if not root.is_dir():
        raise SkillAccessError("The bound skill library is not a readable directory.")
    return root


def _skills(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir() or child.is_symlink():
            continue
        if not _SKILL_NAME.fullmatch(child.name):
            continue
        if (child / "SKILL.md").is_file():
            found[child.name] = child
    return found


def _read(root: Path, name: str, relative_file: str) -> tuple[str, dict[str, Any]]:
    name = str(name or "").strip().lower()
    if not _SKILL_NAME.fullmatch(name):
        raise SkillAccessError("Skill names use lowercase letters, digits, '-' or '_'.")
    skills = _skills(root)
    skill_dir = skills.get(name)
    if skill_dir is None:
        available = ", ".join(sorted(skills)) or "none"
        raise SkillAccessError(f"Skill {name!r} not found. Available skills: {available}")
    relative_file = str(relative_file or "SKILL.md").strip() or "SKILL.md"
    candidate = Path(relative_file)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SkillAccessError("Skill file paths must stay inside the skill package.")
    target = (skill_dir / candidate).resolve()
    if target != skill_dir and skill_dir not in target.parents:
        raise SkillAccessError("Skill file path escapes the skill package.")
    if not target.is_file():
        files = [
            path.relative_to(skill_dir).as_posix()
            for path in sorted(skill_dir.rglob("*"))
            if path.is_file()
        ]
        shown = ", ".join(files[:_MAX_FILE_LIST]) or "none"
        if len(files) > _MAX_FILE_LIST:
            shown += f", … ({len(files) - _MAX_FILE_LIST} more)"
        raise SkillAccessError(
            f"File {relative_file!r} does not exist in skill {name!r}; files: {shown}"
        )
    text = target.read_text(encoding="utf-8")
    if len(text) > _MAX_SKILL_CHARS:
        text = text[:_MAX_SKILL_CHARS]
    return text, {
        "skill": name,
        "file": target.relative_to(skill_dir).as_posix(),
        "char_count": len(text),
    }


class ReadSkillTool(BaseTool):
    definition = ToolDefinition(
        name="read_skill",
        description=(
            "Read a skill's full playbook (SKILL.md) or one of its reference "
            "files. Call this before attempting a task that matches a listed skill."
        ),
        parameters=(
            ToolParameter(
                name="name",
                type="string",
                description="Exact skill name as listed in the Skills section.",
            ),
            ToolParameter(
                name="file",
                type="string",
                description="Optional relative file inside the skill; defaults to SKILL.md.",
                required=False,
            ),
        ),
    )
    scopes = ("skills:read",)
    read_only = True

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        context.check_cancelled()
        try:
            text, metadata = _read(
                _root(context),
                str(arguments.get("name") or ""),
                str(arguments.get("file") or "SKILL.md"),
            )
        except (SkillAccessError, OSError, UnicodeDecodeError) as exc:
            return ToolResult(
                content=str(exc),
                success=False,
                metadata={"error": "skill_access", "detail": str(exc)},
            )
        return ToolResult(content=text, metadata=metadata)


class LoadToolsTool(BaseTool):
    definition = ToolDefinition(
        name="load_tools",
        description=(
            "Load one or more Extended Tools so their schemas become callable "
            "in this turn and session. Call this before using an extended tool."
        ),
        parameters=(
            ToolParameter(
                name="names",
                type="array",
                description="Exact deferred tool names to load.",
                items={"type": "string"},
            ),
        ),
    )
    scopes = ("tools:load",)
    read_only = True

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        context.check_cancelled()
        loader = context.state.get("deferred_loader")
        if not isinstance(loader, DeferredToolLoader):
            return ToolResult(
                content="(load_tools is unavailable in this context)",
                success=False,
                metadata={"error": "no_deferred_loader"},
            )
        names = arguments.get("names")
        if not isinstance(names, list) or not names:
            return ToolResult(
                content="load_tools requires a non-empty `names` array.",
                success=False,
                metadata={"error": "invalid_arguments"},
            )
        outcome = loader.load(names)
        parts: list[str] = []
        if outcome["loaded"]:
            parts.append("Loaded (now callable): " + ", ".join(outcome["loaded"]))
        if outcome["already_loaded"]:
            parts.append("Already loaded: " + ", ".join(outcome["already_loaded"]))
        if outcome["unknown"]:
            parts.append(
                "Unknown: "
                + ", ".join(outcome["unknown"])
                + " (use exact names from the Extended Tools section)"
            )
        return ToolResult(
            content="\n".join(parts) or "(nothing to load)",
            success=not outcome["unknown"] or bool(outcome["loaded"]),
            metadata=dict(outcome),
        )


__all__ = ["LoadToolsTool", "ReadSkillTool", "SkillAccessError"]
