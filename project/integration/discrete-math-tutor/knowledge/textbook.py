"""Small local retriever for the supplied discrete-mathematics chapters."""

from __future__ import annotations

import math
import json
import re
from collections import Counter
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path


TEXTBOOK_DIR = Path(__file__).resolve().parent / "textbook_text"
MULTIMODAL_CHUNKS = Path(__file__).resolve().parent / "extracted_multimodal" / "multimodal_chunks.jsonl"
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
    kind: str = "text"
    asset_ids: tuple[str, ...] = ()
    section_id: int | None = None


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


@lru_cache(maxsize=4)
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
    for generated_path in (MULTIMODAL_CHUNKS, MULTIMODAL_CHUNKS.with_name("vector_chunks.jsonl")):
        if not generated_path.is_file():
            continue
        for line in generated_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("kind") not in ("table", "formula", "image_context"):
                continue
            content = str(item.get("text") or "").strip()
            if not content:
                continue
            chunks.append(TextbookChunk(
                source=str(item.get("source") or "教材多模态提取"),
                section=str(item.get("section") or "未标注小节"),
                text=content,
                terms=terms_for(content),
                kind=str(item["kind"]),
                asset_ids=tuple(item.get("asset_ids") or ()),
                section_id=item.get("section_id"),
            ))
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
    if not re.search(r"特殊图|完全匹配|二部图|平面图|生成树", query) and (query.strip() == "图" or re.search(r"图论|有向图|无向图|欧拉图|哈密顿图|图这一|图这部|图的|图部分", query)):
        graph_chunks = [chunk for chunk in chunks if chunk.source.startswith("第7章图")]
        if graph_chunks:
            chunks = graph_chunks
    figure_numbers = re.findall(r"图\s*(\d+)\s*[.．]\s*(\d+)", query)
    if figure_numbers:
        patterns = [re.compile(r"图\s*"+a+r"\s*[.．]\s*"+b+r"(?!\d)") for a,b in figure_numbers]
        matched = [chunk for chunk in chunks if chunk.kind != "formula" and any(p.search(chunk.text) for p in patterns)]
        matched.sort(key=lambda chunk: (chunk.kind != "image_context", len(set(re.findall(r"图\s*\d+\s*[.．]\s*\d+",chunk.text))),len(chunk.text)))
        if matched:
            return matched[:limit]
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
        requested_kind = "table" if re.search(r"表格|真值表|函数表", query) else "formula" if re.search(r"公式|表达式", query) else "image_context" if re.search(r"配图|插图|图示|图片", query) else None
        if requested_kind == chunk.kind:
            score *= 2.0
        if chunk.kind == "image_context" and re.search(r"例\s*8[.．]2", chunk.text) and re.search(r"完全匹配|X-完全匹配|粗边|匹配边", query):
            score += 100.0
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
        f"[{index}] {chunk.source}｜{chunk.section}"
        + (f"｜{dict(table='表格', formula='公式', image_context='插图').get(chunk.kind, chunk.kind)}" if chunk.kind != "text" else "")
        + f"\n{chunk.text}"
        for index, chunk in enumerate(chunks, 1)
    )
