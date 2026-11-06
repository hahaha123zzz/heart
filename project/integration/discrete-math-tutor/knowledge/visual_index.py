"""教材图表索引的解析与按章/节查询。索引只负责选择，不保存图片。"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from knowledge.textbook import terms_for

INDEX_PATH = Path(__file__).resolve().parent / "course_visual_index.md"
CN_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
              "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11,
              "十二": 12, "十三": 13, "十四": 14, "十五": 15}
CHAPTER = re.compile(r"^##\s*第\s*(\d+|[一二三四五六七八九十]+)\s*章\s*(.*)$")
SECTION = re.compile(r"^###\s*第\s*(\d+|[一二三四五六七八九十]+)\s*节\s*(.*)$")
LABEL = re.compile(r"(图|表)\s*(\d+)\s*[-.．]\s*(\d+)")
PAGE = re.compile(r"^p\.\s*(\d+|-)$")


def number_from_text(token: str) -> int:
    token = token.strip()
    if token.isdigit():
        return int(token)
    return CN_NUMBERS.get(token, 0)


@dataclass(frozen=True)
class VisualEntry:
    chapter_id: int
    chapter_title: str
    section_id: int
    section_title: str
    kind: str
    label: str
    type: str
    page: int | None
    name: str
    knowledge_points: tuple[str, ...]
    content: str
    use_for: str
    asset_id: str | None
    blocks: tuple[int, ...]
    status: str
    raw: str

    def line(self) -> str:
        return self.raw


@dataclass(frozen=True)
class VisualIndex:
    entries: tuple[VisualEntry, ...]

    def lookup(self, *, chapter_id: int | None, section_id: int | None,
               query: str = "", limit: int = 8) -> list[VisualEntry]:
        """全书按语义检索；当前章/节只加权，不做硬过滤。空查询才返回当前范围目录。"""
        query = query or ""
        named = {f"{a}{b}-{c}" for a, b, c in LABEL.findall(query)}
        if named:
            exact = [entry for entry in self.entries if entry.label.replace(" ", "") in named]
            if exact:
                return exact[:limit]
            # 合并表/复合图可能把别名写在名称或内容里，按别名回查一次。
            return [entry for entry in self.entries
                    if any(label in f"{entry.name}{entry.content}{entry.use_for}" for label in named)][:limit]
        if not query.strip():
            if section_id is not None and chapter_id is not None:
                return [entry for entry in self.entries
                        if entry.chapter_id == chapter_id and entry.section_id == section_id][:limit]
            if chapter_id is not None:
                return [entry for entry in self.entries if entry.chapter_id == chapter_id][:limit]
            return []
        matched = _rank(self.entries, query, limit, chapter_id=chapter_id, section_id=section_id)
        if matched:
            return matched
        if section_id is not None and chapter_id is not None:
            return [entry for entry in self.entries
                    if entry.chapter_id == chapter_id and entry.section_id == section_id][:limit]
        if chapter_id is not None:
            return [entry for entry in self.entries if entry.chapter_id == chapter_id][:limit]
        return []


def _rank(entries: list[VisualEntry] | tuple[VisualEntry, ...], query: str, limit: int,
          *, chapter_id: int | None = None, section_id: int | None = None) -> list[VisualEntry]:
    qterms = terms_for(query)
    scored = []
    for order, entry in enumerate(entries):
        haystack = " ".join((entry.name, *entry.knowledge_points, entry.content, entry.use_for))
        score = len(qterms & terms_for(haystack))
        if any(point and (point in query or query in point) for point in entry.knowledge_points):
            score += 3
        if score and chapter_id is not None and entry.chapter_id == chapter_id:
            score += 3
            if section_id is not None and entry.section_id == section_id:
                score += 4
        if score:
            scored.append((score, order, entry))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [entry for _, _, entry in scored[:limit]]


def _value(parts: list[str], key: str) -> str:
    for separator in ("：", ":"):
        prefix = key + separator
        for part in parts:
            if part.startswith(prefix):
                return part[len(prefix):].strip()
    return ""


def _parse_entry(line: str, chapter_id: int, chapter_title: str,
                 section_id: int, section_title: str) -> VisualEntry | None:
    body = line[2:].strip() if line.startswith("- ") else ""
    if not body:
        return None
    parts = [part.strip() for part in body.split("｜")]
    label = parts[0]
    if not label.startswith(("图", "表", "无编号")):
        return None
    page_index = next((index for index, part in enumerate(parts) if PAGE.match(part)), None)
    if page_index is None:
        type_value = parts[1] if len(parts) > 1 else ""
        name = parts[2] if len(parts) > 2 else ""
        page = None
    else:
        type_value = parts[1] if len(parts) > 1 else ""
        name = parts[page_index + 1] if len(parts) > page_index + 1 else ""
        raw_page = PAGE.match(parts[page_index]).group(1)
        page = int(raw_page) if raw_page.isdigit() else None
    points = tuple(point.strip() for point in _value(parts, "知识点").split("、") if point.strip())
    blocks = tuple(int(value) for value in re.findall(r"\d+", _value(parts, "blocks")))
    asset_id = _value(parts, "asset_id") or None
    entry_kind = "表" if label.startswith("表") else ("图" if label.startswith("图") else "无编号")
    return VisualEntry(
        chapter_id=chapter_id, chapter_title=chapter_title,
        section_id=section_id, section_title=section_title,
        kind=entry_kind, label=label.replace(" ", ""), type=type_value, page=page,
        name=name, knowledge_points=points, content=_value(parts, "内容"),
        use_for=_value(parts, "用于"), asset_id=asset_id, blocks=blocks,
        status=_value(parts, "状态") or "待核", raw=body,
    )


def parse_index(text: str) -> VisualIndex:
    entries: list[VisualEntry] = []
    chapter_id = 0
    chapter_title = ""
    section_id = 0
    section_title = ""
    for line in text.splitlines():
        chapter = CHAPTER.match(line)
        if chapter:
            chapter_id, chapter_title = number_from_text(chapter.group(1)), chapter.group(2).strip()
            section_id, section_title = 0, ""
            continue
        section = SECTION.match(line)
        if section:
            section_id, section_title = number_from_text(section.group(1)), section.group(2).strip()
            continue
        if line.startswith("- ") and chapter_id and section_id:
            entry = _parse_entry(line, chapter_id, chapter_title, section_id, section_title)
            if entry:
                entries.append(entry)
    return VisualIndex(tuple(entries))


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> VisualIndex:
    return parse_index(Path(path).read_text(encoding="utf-8"))


def load_index(path: str | Path | None = None) -> VisualIndex:
    target = Path(path) if path else INDEX_PATH
    if not target.is_file():
        return VisualIndex(())
    return _load(str(target.resolve()), target.stat().st_mtime)


def clear_cache() -> None:
    _load.cache_clear()


def format_entries(entries: list[VisualEntry]) -> str:
    return "\n".join(entry.line() for entry in entries)


__all__ = ["INDEX_PATH", "VisualEntry", "VisualIndex", "clear_cache",
           "format_entries", "load_index", "parse_index"]
