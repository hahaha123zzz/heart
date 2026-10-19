"""Authorization and resource scope for one tool turn.

The upstream runtime keeps account/course grants outside the tool protocol and
filters the manifest before dispatch.  Q4 keeps that split, but makes the
execution-time check explicit as well: a name that was never mounted, or a
resource scope that was not granted, is refused at ``execute`` rather than
merely omitted from the prompt.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Allowlist:
    """Allowed names, or unrestricted when :attr:`names` is ``None``."""

    names: frozenset[str] | None = None

    @classmethod
    def unrestricted(cls) -> "Allowlist":
        return cls(names=None)

    @classmethod
    def of(cls, names: Iterable[str] | None) -> "Allowlist":
        if names is None:
            return cls(names=None)
        return cls(names=frozenset(str(name) for name in names))

    @property
    def is_unrestricted(self) -> bool:
        return self.names is None

    def allows(self, name: str) -> bool:
        return self.names is None or name in self.names

    def narrow(self, other: "Allowlist") -> "Allowlist":
        if self.names is None:
            return other
        if other.names is None:
            return self
        return Allowlist(names=self.names & other.names)

    def widen(self, extra: Iterable[str]) -> "Allowlist":
        if self.names is None:
            return self
        return Allowlist(names=self.names | frozenset(str(name) for name in extra))

    def as_set(self) -> set[str] | None:
        return None if self.names is None else set(self.names)


@dataclass(frozen=True, slots=True)
class ToolGrant:
    """Per-turn tool and resource grant.

    ``tools`` gates tool names.  ``scopes`` gates declared resource scopes
    (for example ``workspace:read``); an empty set grants none.  Roots are
    resolved by the task layer and must never come from model-authored args.
    """

    tools: Allowlist = field(default_factory=lambda: Allowlist.of(()))
    scopes: frozenset[str] = frozenset()
    workspace_root: Path | None = None
    skills_root: Path | None = None

    def allows_tool(self, name: str) -> bool:
        return self.tools.allows(name)

    def allows_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def allows_scopes(self, required: Iterable[str]) -> bool:
        return all(self.allows_scope(scope) for scope in required)

    def narrow(self, other: "ToolGrant") -> "ToolGrant":
        if (
            self.workspace_root is not None
            and other.workspace_root is not None
            and self.workspace_root.resolve() != other.workspace_root.resolve()
        ):
            raise ValueError("Cannot narrow grants with different workspace roots")
        if (
            self.skills_root is not None
            and other.skills_root is not None
            and self.skills_root.resolve() != other.skills_root.resolve()
        ):
            raise ValueError("Cannot narrow grants with different skill roots")
        return ToolGrant(
            tools=self.tools.narrow(other.tools),
            scopes=self.scopes & other.scopes,
            workspace_root=other.workspace_root or self.workspace_root,
            skills_root=other.skills_root or self.skills_root,
        )


@dataclass(frozen=True, slots=True)
class ToolScope:
    """Trusted execution context for one student/course/task turn."""

    student_id: str
    course_id: str = ""
    session_id: str = ""
    request_id: str = ""
    grant: ToolGrant = field(default_factory=ToolGrant)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def allows_tool(self, name: str) -> bool:
        return self.grant.allows_tool(name)

    def allows_definition(self, *, name: str, scopes: Iterable[str]) -> bool:
        return self.grant.allows_tool(name) and self.grant.allows_scopes(scopes)

    def with_grant(self, grant: ToolGrant) -> "ToolScope":
        return ToolScope(
            student_id=self.student_id,
            course_id=self.course_id,
            session_id=self.session_id,
            request_id=self.request_id,
            grant=grant,
            metadata=dict(self.metadata),
        )


__all__ = ["Allowlist", "ToolGrant", "ToolScope"]
