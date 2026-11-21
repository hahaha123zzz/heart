"""Offline semantic section suggestions; never used by the active answer path."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path


INDEX = Path(__file__).resolve().parent / "rag_index_v2.sqlite3"
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


@dataclass(frozen=True)
class SemanticCandidate:
    chapter_id: int
    section_id: int
    title: str
    score: float


def _unit(vector) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return tuple(value / norm for value in values)


def _dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right))


class SemanticSectionShadow:
    """Embed textbook chunks once and pool their scores by section."""

    def __init__(
        self,
        *,
        index_path: Path | None = None,
        model_name: str = DEFAULT_MODEL,
        cache_dir: str | None = None,
    ) -> None:
        self.index_path = INDEX if index_path is None else index_path
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._vectors: list[tuple[int, int, str, tuple[float, ...]]] = []

    def _load(self) -> None:
        if self._vectors:
            return
        from fastembed import TextEmbedding

        with sqlite3.connect(self.index_path) as db:
            rows = db.execute(
                "SELECT chapter_id,section_id,section,text FROM chunks "
                "WHERE section_id IS NOT NULL ORDER BY chapter_id,section_id,id"
            ).fetchall()
        documents = [
            f"{title}\n{text[:900]}"
            for chapter_id, section_id, title, text in rows
        ]
        kwargs = {"cuda": False}
        if self.cache_dir:
            kwargs["cache_dir"] = self.cache_dir
        self._model = TextEmbedding(model_name=self.model_name, **kwargs)
        vectors = self._model.embed(documents, batch_size=32)
        self._vectors = [
            (int(chapter_id), int(section_id), title, _unit(vector))
            for (chapter_id, section_id, title, _), vector in zip(rows, vectors)
        ]

    def predict(self, query: str, *, limit: int = 3) -> tuple[SemanticCandidate, ...]:
        self._load()
        assert self._model is not None
        query_vector = _unit(next(iter(self._model.embed([query]))))
        best: dict[tuple[int, int, str], float] = {}
        for chapter_id, section_id, title, vector in self._vectors:
            key = (chapter_id, section_id, title)
            best[key] = max(best.get(key, -1.0), _dot(query_vector, vector))
        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)[:limit]
        return tuple(
            SemanticCandidate(
                chapter_id=chapter_id,
                section_id=section_id,
                title=title,
                score=round(score, 6),
            )
            for (chapter_id, section_id, title), score in ranked
        )
