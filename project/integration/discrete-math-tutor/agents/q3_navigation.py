"""Q3 learning-navigation boundary.

Q3 resolves a learning target before it asks a tool to search. Q2 owns how
the target is selected and how textbook sources are retrieved; this module
only defines the project-local protocol plus a deterministic stub for loop
tests. It never parses chapters or invents a next target.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Callable, Protocol, Literal


@dataclass(frozen=True)
class LearningTarget:
    target_id: str
    name: str
    chapter_id: int | None = None
    section_id: int | None = None
    source_scope: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    version: str = ""


@dataclass(frozen=True)
class NavigationDecision:
    action: Literal["teach", "next", "previous", "clarify", "out_of_scope"]
    target: LearningTarget | None = None
    missing: tuple[str, ...] = ()
    reason: str = ""
    version: str = ""


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    document_id: str
    text: str
    version: str = ""
    chapter_id: int | None = None
    section_id: int | None = None
    page: int | None = None
    quote: str = ""
    image_refs: list[dict[str, Any]] = field(default_factory=list)
    location: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_id": self.document_id,
            "text": self.text,
            "version": self.version,
            "chapter_id": self.chapter_id,
            "section_id": self.section_id,
            "page": self.page,
            "quote": self.quote,
            "image_refs": list(self.image_refs),
            "location": dict(self.location),
        }


class LearningNavigator(Protocol):
    def resolve(self, *, message: str, student_id: str, session_id: str,
                current_target: LearningTarget | None, context: Any) -> NavigationDecision: ...

    def search(self, *, target: LearningTarget, query: str, limit: int,
               preferred_types: tuple[str, ...] = ()) -> list[SourceRef]: ...


class StubLearningNavigator:
    """Deterministic substitute retrieval; every source is marked ``stub``."""

    def __init__(self, *, target: LearningTarget | None = None,
                 next_target: LearningTarget | None = None,
                 sources: list[SourceRef] | None = None) -> None:
        self.target = target
        self.next_target = next_target
        self.sources = list(sources or [])
        self.calls: list[tuple[str, str]] = []

    def resolve(self, *, message: str, student_id: str, session_id: str,
                current_target: LearningTarget | None, context: Any) -> NavigationDecision:
        base = current_target or self.target
        self.calls.append(("resolve", message))
        if any(token in message for token in ("下一", "下一个", "下一步", "next")):
            if self.next_target is not None:
                return NavigationDecision("next", self.next_target,
                                          reason="stub next target")
            return NavigationDecision("clarify", base, missing=("target",),
                                      reason="课程路径尚未提供下一目标")
        if base is None:
            return NavigationDecision("clarify", None, missing=("target",),
                                      reason="当前没有明确学习目标")
        return NavigationDecision("teach", base, reason="沿用当前目标")

    def search(self, *, target: LearningTarget, query: str, limit: int,
               preferred_types: tuple[str, ...] = ()) -> list[SourceRef]:
        self.calls.append(("search", target.target_id))
        return [SourceRef(**{**source.to_dict(), "location": {**source.location, "stub": True}})
                for source in self.sources[:limit]]


class CallbackNavigator:
    """Adapter for Q2: target resolution and search are injected callbacks."""

    def __init__(self, *,
                 resolve_fn: Callable[..., NavigationDecision] | None = None,
                 search_fn: Callable[..., list[SourceRef | dict[str, Any]]] | None = None,
                 next_target_fn: Callable[..., LearningTarget | None] | None = None) -> None:
        self.resolve_fn = resolve_fn
        self.search_fn = search_fn
        self.next_target_fn = next_target_fn
        self.calls: list[tuple[str, str]] = []

    def resolve(self, *, message: str, student_id: str, session_id: str,
                current_target: LearningTarget | None, context: Any) -> NavigationDecision:
        self.calls.append(("resolve", message))
        if self.resolve_fn is not None:
            return self.resolve_fn(message=message, student_id=student_id,
                                   session_id=session_id, current_target=current_target,
                                   context=context)
        if any(token in message for token in ("下一", "下一个", "下一步", "next")):
            target = self.next_target_fn(message=message, current_target=current_target,
                                         context=context) if self.next_target_fn else None
            if target is None:
                return NavigationDecision("clarify", current_target, missing=("target",),
                                          reason="课程路径尚未提供下一目标")
            return NavigationDecision("next", target, reason="课程路径的下一目标")
        if current_target is None:
            return NavigationDecision("clarify", None, missing=("target",),
                                      reason="当前没有明确学习目标")
        return NavigationDecision("teach", current_target, reason="沿用当前目标")

    def search(self, *, target: LearningTarget, query: str, limit: int,
               preferred_types: tuple[str, ...] = ()) -> list[SourceRef]:
        self.calls.append(("search", target.target_id))
        if self.search_fn is None:
            return []
        rows = self.search_fn(target=target, query=query, limit=limit,
                              preferred_types=preferred_types)
        result = []
        for row in rows:
            if isinstance(row, SourceRef):
                result.append(row)
            elif isinstance(row, dict):
                result.append(SourceRef(
                    source_id=str(row.get("source_id") or row.get("chunk_id") or ""),
                    document_id=str(row.get("document_id") or row.get("source") or ""),
                    text=str(row.get("text") or ""),
                    version=str(row.get("version") or ""),
                    chapter_id=row.get("chapter_id"),
                    section_id=row.get("section_id"),
                    page=row.get("page"),
                    quote=str(row.get("quote") or ""),
                    image_refs=list(row.get("image_refs") or []),
                    location=dict(row.get("location") or {}),
                ))
        return result[:limit]


def source_from_chunk(chunk: Any, index: int) -> SourceRef:
    """Map a Q2/TextbookChunk-like source to the authoritative release record.

    Local RAG chunks usually carry a readable source filename but no document
    id/version.  Citation display compares both against Q2's document registry;
    leaving them empty makes every later history card look stale.  Use the Q2
    chapter record only when its source file matches, otherwise keep the chunk
    identity rather than inventing a version.
    """
    text = str(getattr(chunk, "text", "") or "")
    source = str(getattr(chunk, "source", "") or "")
    chapter_id = getattr(chunk, "chapter_id", None)
    record = None
    if chapter_id is not None:
        try:
            from knowledge.pdf_reader import document_for_chapter
            candidate = document_for_chapter(int(chapter_id))
            if candidate and (not source or Path(candidate["source"]).stem == Path(source).stem):
                record = candidate
        except (ImportError, OSError, ValueError, TypeError):
            record = None
    document_id = str((record or {}).get("document_id") or getattr(chunk, "document_id", "") or source)
    version = str((record or {}).get("version") or getattr(chunk, "version", "") or "")
    source_file = str((record or {}).get("source") or source)
    source_id = str(getattr(chunk, "id", "") or getattr(chunk, "chunk_id", "") or "")
    if not source_id:
        source_id = hashlib.sha256((source + "\0" + text).encode("utf-8")).hexdigest()[:16]
    return SourceRef(
        source_id=source_id,
        document_id=document_id,
        text=text,
        version=version,
        chapter_id=chapter_id,
        section_id=getattr(chunk, "section_id", None),
        page=getattr(chunk, "page", None),
        quote=str(getattr(chunk, "quote", "") or text[:160]),
        location={"origin": "q2_chunk", "index": index,
                  "source_file": source_file, "document_version": version},
    )


__all__ = [
    "CallbackNavigator", "LearningNavigator", "LearningTarget",
    "NavigationDecision", "SourceRef", "StubLearningNavigator", "source_from_chunk",
]
