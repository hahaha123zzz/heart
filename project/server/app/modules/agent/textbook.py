"""Small local retriever for the supplied discrete-mathematics chapters."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


TEXTBOOK_DIR = Path(__file__).resolve().parents[3] / "data" / "textbook_text"
HEADING = re.compile(
    r"^(?:第\s*\d+\s*章|\d+(?:\.\d+){1,3})\s*[\u4e00-\u9fff][^\n]{0,80}$"
)
HAN = re.compile(r"[\u4e00-\u9fff]+")
LATIN = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{1,}")
QUERY_FILLER = frozenset(
    {"什么", "怎么", "如何", "一下", "请问", "给我", "帮我", "解释", "教材", "例子", "定义", "区别"}
)


@dataclass(frozen=True)
class TextbookChunk:
    source: str
    section: str
    text: str
    terms: frozenset[str]


def terms_for(text: str) -> frozenset[str]:
    result: set[str] = set()
    for run in HAN.findall(text):
        for size in (2, 3):
            result.update(
                run[i : i + size]
                for i in range(max(0, len(run) - size + 1))
            )
    result.update(word.lower() for word in LATIN.findall(text))
    return frozenset(result - QUERY_FILLER)


def load_textbook(directory: Path = TEXTBOOK_DIR) -> list[TextbookChunk]:
    if not directory.is_dir():
        raise FileNotFoundError(f"教材文字目录不存在：{directory}")
    files = sorted(directory.glob("*.txt"))
    if len(files) != 10:
        raise RuntimeError(f"教材应有 10 章，当前只有 {len(files)} 章")

    chunks: list[TextbookChunk] = []
    for path in files:
        section = path.stem
        buffer: list[str] = []

        def flush() -> None:
            if not buffer:
                return
            content = "\n".join(buffer).strip()
            buffer.clear()
            if len(content) >= 40:
                chunks.append(
                    TextbookChunk(path.name, section, content, terms_for(content))
                )

        for original in path.read_text(encoding="utf-8").splitlines():
            line = original.strip()
            if not line:
                continue
            if HEADING.match(line):
                flush()
                section = line
                continue
            if len(line) > 800:
                flush()
                for start in range(0, len(line), 650):
                    part = line[start : start + 650]
                    if len(part) >= 40:
                        chunks.append(
                            TextbookChunk(path.name, section, part, terms_for(part))
                        )
                continue
            if sum(map(len, buffer)) + len(line) > 650:
                flush()
            buffer.append(line)
        flush()
    if not chunks:
        raise RuntimeError("教材没有可检索的文字")
    return chunks


def retrieve(
    query: str,
    chunks: list[TextbookChunk],
    *,
    limit: int = 3,
) -> list[TextbookChunk]:
    query = query.replace("并与交", "并集与交集").replace("交与并", "交集与并集")
    # A one-character chapter title such as “图” is lost by n-gram tokenization.
    # Prefer its own chapter when the student clearly asks about graph theory.
    if query.strip() == "图" or re.search(r"图论|有向图|无向图|欧拉图|哈密顿图|图这一|图这部|图的|图部分", query):
        graph_chunks = [chunk for chunk in chunks if chunk.source.startswith("第7章图")]
        if graph_chunks:
            chunks = graph_chunks
    query_terms = terms_for(query)
    if query.strip() == "图":
        query_terms = terms_for("图论 图的基本概念")
    if not query_terms:
        return []
    document_frequency = Counter(
        term for chunk in chunks for term in chunk.terms if term in query_terms
    )
    ranking: list[tuple[float, TextbookChunk]] = []
    for chunk in chunks:
        matches = query_terms & chunk.terms
        if not matches:
            continue
        score = sum(
            math.log(1 + (len(chunks) + 1) / (document_frequency[term] + 1))
            * (1.4 if len(term) == 3 else 1.0)
            for term in matches
        )
        source_matches = query_terms & terms_for(chunk.source)
        section_matches = query_terms & terms_for(chunk.section)
        score += 10.0 * len(source_matches) + 4.0 * len(section_matches)
        section_label = re.sub(r"^\d+(?:\.\d+)*\s*", "", chunk.section).strip()
        if section_label in query_terms:
            score += 10.0
        if "[公式或对象]" in chunk.text:
            score *= 0.82
        ranking.append((score, chunk))

    ranking.sort(key=lambda item: item[0], reverse=True)
    selected: list[TextbookChunk] = []
    per_source: Counter[str] = Counter()
    for _, chunk in ranking:
        if per_source[chunk.source] >= 2:
            continue
        selected.append(chunk)
        per_source[chunk.source] += 1
        if len(selected) == limit:
            break
    return selected


def format_excerpts(chunks: list[TextbookChunk]) -> str:
    if not chunks:
        return "没有检索到相关教材文字。"
    return "\n\n".join(
        f"[{index}] {chunk.source}｜{chunk.section}\n{chunk.text}"
        for index, chunk in enumerate(chunks, 1)
    )
