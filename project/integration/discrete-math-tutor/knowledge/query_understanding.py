"""Resolve a textbook question to likely sections before retrieval."""

from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from knowledge.answer_ranking import question_kind


INDEX = Path(__file__).resolve().parent / "rag_index_v2.sqlite3"

ALIASES = (
    ("并排顺序", "排列"),
    ("子集合", "子集"),
    ("结点", "顶点"),
    ("笛卡儿积", "笛卡尔积"),
    ("组合数", "组合"),
    ("并集", "并"),
    ("交集", "交"),
    ("补集", "补"),
)

QUESTION_PATTERNS = (
    r"是什么意思",
    r"是什么",
    r"什么是",
    r"需要满足什么条件",
    r"满足哪些条件",
    r"有什么特点",
    r"包含哪些.{0,6}",
    r"由哪一类.{0,6}组成",
    r"由哪些.{0,6}组成",
    r"是什么关系",
    r"有什么关系",
    r"怎么样",
    r"怎样",
    r"如何",
    r"为什么",
    r"为何",
    r"什么时候",
    r"哪些",
    r"哪一类",
    r"哪类",
)

QUERY_FILLER = (
    r"什么|怎么|怎么样|怎样|如何|为什么|为何|是否|请问|请解释|解释一下|解释|"
    r"一下|定义|含义|内容|特点|条件|时候|可以|需要|满足|具有|包含哪些|哪些|"
    r"哪类|哪一类|一个|这个|这些|会|能|之间|分别|各自|由|组成|对象|的是|"
    r"是|的|了|吗|呢|中|里|在|指|范围|一共|多少|有"
)

KEY_CHARS = frozenset("树图并交差补度")
BROAD_UNITS = frozenset({
    "集合", "关系", "命题", "真值", "函数", "公式", "性质", "表示",
    "基本", "概念", "形式系统", "谓词公式", "逻辑", "数学", "计数", "元素",
})


@dataclass(frozen=True)
class SectionCandidate:
    chapter_id: int
    section_id: int
    title: str
    score: float
    concepts: tuple[str, ...]


@dataclass(frozen=True)
class QueryUnderstanding:
    original: str
    normalized: str
    intent: str
    related_concepts: tuple[str, ...]
    candidates: tuple[SectionCandidate, ...]
    retrieval_query: str
    needs_clarification: bool = False
    clarification: str = ""


@dataclass(frozen=True)
class _SectionEntry:
    chapter_id: int
    section_id: int
    title: str
    normalized: str
    concepts: tuple[str, ...]
    depth: int


def _normalize(value: str, *, title: bool = False) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    if title:
        text = re.sub(
            r"^(?:第\s*\d+\s*章|\d+(?:\.\d+){1,3})\s*",
            "",
            text,
        )
    for source, target in ALIASES:
        text = text.replace(source, target)
    return re.sub(r"[\s“”「」\"'，。！？；：,.!?;:()（）【】\[\]+\-—/_]+", "", text)


def _focus(value: str) -> str:
    text = _normalize(value)
    for pattern in QUESTION_PATTERNS:
        text = re.sub(pattern, "", text)
    return re.sub(QUERY_FILLER, "", text)


def _related_concepts(value: str) -> tuple[str, ...]:
    text = _normalize(value)
    concepts: list[str] = []
    if ("集合" in text and re.search(r"互换.*成员|成员.*相同|元素.*相同|只.*成员", text)):
        concepts.extend(("外延性公理", "集合相等"))
    if re.search(r"去掉.*共同元素|A-B|A－B", text):
        concepts.extend(("差集", "差运算"))
    if re.search(r"所有.*子集.*(?:汇合|集合)|全部子集", text):
        concepts.append("幂集")
    if "子集" in text and re.search(r"多少|几个|个数|总数|数量", text):
        concepts.append("幂集")
    if "矛盾式" in text and "真值" in text:
        concepts.append("重言式")
    if re.search(r"递归.*定义", text) and re.search(r"基础|构造", text):
        concepts.extend(("结构归纳", "归纳基础", "归纳推理"))
    if re.search(r"方案.*互斥|几类方案|分类", text):
        concepts.append("加法原理")
    if re.search(
        r"并.*(?:大小|元素个数|数量).*(?:相加|直接加)|"
        r"(?:并|交叠).*(?:重复|重叠)",
        text,
    ):
        concepts.extend(("包含排斥原理", "交集"))
    if re.search(r"不计.*次序|不计.*顺序|先后次序", text):
        concepts.extend(("组合", "组合的计数"))
    if re.search(r"至少一个.*真|一个为真", text):
        concepts.extend(("析取", "逻辑联结词"))
    if "析取子句" in text:
        concepts.extend(("析取子句", "析取范式", "合取范式"))
    if "合取子句" in text:
        concepts.extend(("合取子句", "析取范式", "合取范式"))
    if "双重否定" in text:
        concepts.extend(("双重否定律", "逻辑等价式"))
    if re.search(r"所有赋值.*真|任意赋值.*真", text):
        concepts.extend(("重言式", "永真式"))
    if re.search(r"边.*横跨.*顶点组|两个.*顶点组.*边", text):
        concepts.append("二分图")
    if re.search(r"连通.*删去.*边.*无圈|连通.*无回路", text):
        concepts.append("生成树")
    return tuple(dict.fromkeys(concepts))


def _concept_units(title: str) -> tuple[str, ...]:
    text = _normalize(title, title=True)
    raw: list[str] = []
    for part in re.split(r"[、，,；;：:与和及]", text):
        if not part:
            continue
        raw.append(part)
        raw.extend(value for value in re.split(r"的", part) if value and value != part)

    result: list[str] = []
    for unit in raw:
        unit = re.sub(
            r"(?:基本概念|基本形式|基本|概念|运算|计数|规定|原理|"
            r"性质|表示|及其|广义|函数)$",
            "",
            unit,
        )
        if not unit or (len(unit) == 1 and unit not in KEY_CHARS):
            continue
        result.append(unit)
        if len(unit) >= 4:
            result.append(unit[:-2])
    return tuple(dict.fromkeys(result))


def _number_depth(title: str) -> int:
    first = title.split(maxsplit=1)[0] if title.split() else ""
    return max(0, len(re.findall(r"\d+", first)) - 1)


@lru_cache(maxsize=4)
def _section_catalog(path_value: str, modified_ns: int) -> tuple[_SectionEntry, ...]:
    del modified_ns
    with closing(sqlite3.connect(path_value)) as db:
        rows = db.execute(
            "SELECT DISTINCT chapter_id,section_id,section FROM chunks "
            "WHERE section_id IS NOT NULL ORDER BY chapter_id,section_id"
        ).fetchall()
    return tuple(
        _SectionEntry(
            chapter_id=int(chapter_id),
            section_id=int(section_id),
            title=title,
            normalized=_normalize(title, title=True),
            concepts=_concept_units(title),
            depth=_number_depth(title),
        )
        for chapter_id, section_id, title in rows
    )


def _catalog(path: Path) -> tuple[_SectionEntry, ...]:
    if not path.is_file():
        return ()
    return _section_catalog(str(path.resolve()), path.stat().st_mtime_ns)


def _idf(catalog: tuple[_SectionEntry, ...]) -> dict[str, float]:
    frequency = Counter(
        concept
        for section in catalog
        for concept in set(section.concepts)
    )
    total = len(catalog)
    return {
        concept: math.log((total + 1) / (count + 1)) + 1
        for concept, count in frequency.items()
    }


def _score_section(
    query: str,
    section: _SectionEntry,
    weights: dict[str, float],
) -> tuple[float, tuple[str, ...]]:
    matched = tuple(
        concept
        for concept in section.concepts
        if concept in query
        and (concept in KEY_CHARS or concept not in BROAD_UNITS)
    )
    score = sum(
        (18.0 if len(concept) == 1
         else len(concept) ** 2 * weights.get(concept, 1.0) * 3)
        for concept in matched
    )
    if len(section.normalized) >= 4 and section.normalized in query:
        score += 100
    if ("重集" in section.normalized
            and not any(term in query for term in ("重集", "重复", "可重复", "重数"))):
        score *= 0.35
    return score + section.depth * 2, matched


def _has_descendant(section: _SectionEntry, catalog: tuple[_SectionEntry, ...]) -> bool:
    match = re.match(r"^(\d+(?:\.\d+)*)", section.title)
    if not match:
        return False
    prefix = match.group(1) + "."
    return any(other.title.split(maxsplit=1)[0].startswith(prefix) for other in catalog)


def rank_sections(
    query: str,
    *,
    limit: int = 3,
    index_path: Path | None = None,
) -> tuple[SectionCandidate, ...]:
    """Return only sections with an explicit, non-generic concept match."""
    path = INDEX if index_path is None else index_path
    catalog = _catalog(path)
    if not catalog:
        return ()
    focus = _focus(query)
    if not focus:
        return ()
    related = _related_concepts(query)
    if related:
        focus += "".join(related)
    weights = _idf(catalog)
    ranked: list[tuple[float, _SectionEntry, tuple[str, ...]]] = []
    for section in catalog:
        if ("重集" in section.normalized
                and not any(term in focus for term in ("重集", "重复", "可重复", "重数"))):
            continue
        score, matched = _score_section(focus, section, weights)
        if not matched:
            continue
        if section.depth <= 1 and _has_descendant(section, catalog):
            score *= 0.5
        ranked.append((score, section, matched))
    ranked.sort(key=lambda item: (item[0], item[1].section_id), reverse=True)
    return tuple(
        SectionCandidate(
            chapter_id=section.chapter_id,
            section_id=section.section_id,
            title=section.title,
            score=round(score, 4),
            concepts=matched,
        )
        for score, section, matched in ranked[:limit]
    )


def understand(query: str, *, index_path: Path | None = None) -> QueryUnderstanding:
    candidates = rank_sections(query, index_path=index_path)
    focus = _focus(query)
    related = _related_concepts(query)
    kind = question_kind(query)
    retrieval_query = query
    if candidates:
        structural = "；".join(candidate.title for candidate in candidates)
        retrieval_query += "\n教材结构候选（用于定位，不是答案）：" + structural
    ambiguous_reference = bool(re.search(r"这样|那样|这个|那个|它|上题|刚才", focus))
    needs_clarification = len(focus) < 2 or (
        not candidates and ambiguous_reference and len(focus) <= 8
    )
    clarification = (
        "你想问教材里的哪个概念、定理或公式？请补充具体名称。"
        if needs_clarification
        else ""
    )
    return QueryUnderstanding(
        original=query,
        normalized=focus,
        intent=kind,
        related_concepts=related,
        candidates=candidates,
        retrieval_query=retrieval_query,
        needs_clarification=needs_clarification,
        clarification=clarification,
    )
