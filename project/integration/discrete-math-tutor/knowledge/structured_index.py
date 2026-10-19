"""从已提取的 Word 块生成可追溯的教材检索单元。"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTRACTED = ROOT / "extracted_multimodal"
CATALOG = ROOT / "exercises" / "catalog.json"
PDF_MANIFEST = ROOT / "pdf" / "manifest.json"
UNIT_START = re.compile(r"^(?:定义|定理|推论|引理|命题|例|证明|证\s|解\s)\s*\d*(?:[.．]\d+)?")
EXERCISE_HEADING = re.compile(r"^\s*(?:习题|练习)\s*\d+(?:[.．]\d+)?\s*$")
SENTENCE_END = re.compile(r"(?<=[。！？；])")


def _exercise_ranges() -> dict[int, list[tuple[int, int]]]:
    if not CATALOG.is_file():
        return {}
    grouped: dict[tuple[int, str], list[int]] = defaultdict(list)
    for question in json.loads(CATALOG.read_text(encoding="utf-8"))["questions"]:
        key = (int(question["chapter_id"]), str(question["group_id"]))
        for block in question.get("blocks", []) + question.get("shared_blocks", []):
            if isinstance(block.get("block_index"), int):
                grouped[key].append(block["block_index"])
    ranges: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (chapter, _), indices in grouped.items():
        if indices:
            ranges[chapter].append((min(indices), max(indices)))
    return ranges


def _parts(text: str, max_chars: int = 760) -> list[str]:
    """长段只在标点处切开，公式和表格不走这一路径。"""
    if len(text) <= max_chars:
        return [text]
    sentences = [part.strip() for part in SENTENCE_END.split(text) if part.strip()]
    result: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            result.append(current)
            current = ""
        if len(sentence) > max_chars:
            for start in range(0, len(sentence), max_chars):
                result.append(sentence[start:start + max_chars])
        else:
            current += sentence
    if current:
        result.append(current)
    return result


def build_records() -> list[dict]:
    """返回小检索单元，保留其父单元、原 Word 块与 PDF 小节页。"""
    from knowledge.course_config import PSYCHOLOGY,PSYCHOLOGY_DIR
    if PSYCHOLOGY:
        from scripts.build_psychology_sample_index import records
        return [row for chapter in range(1,12)
                for row in records(PSYCHOLOGY_DIR/'chapters'/f'chapter_{chapter:02d}',chapter)]
    exercise_ranges = _exercise_ranges()
    manifests = {int(item["chapter_id"]): item for item in json.loads(PDF_MANIFEST.read_text(encoding="utf-8"))}
    records: list[dict] = []
    block_sections: dict[int, dict[int, dict]] = {}
    for chapter in range(1, 11):
        path = EXTRACTED / f"chapter_{chapter:02d}.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        source = next(ROOT.glob(f"textbook_text/第{chapter}章*.txt")).name
        sections = {int(item["id"]): item for item in manifests[chapter]["sections"]}
        by_title = {re.sub(r"\s+", "", item["title"]): item for item in sections.values()}
        current_section = sections[1]
        positions: dict[int, dict] = {}
        pending: list[dict] = []

        def flush() -> None:
            if not pending:
                return
            first = pending[0]
            title = first["section_title"]
            parent_id = f"ch{chapter}-b{first['block_index']}"
            text = "\n".join(item["text"] for item in pending).strip()
            indices = [item["block_index"] for item in pending]
            assets = list(dict.fromkeys(asset for item in pending for asset in item["asset_ids"]))
            # 原 Word 中有些公式仅有对象，没有文本；用显式 ID 保留可检索入口。
            if assets:
                text += "\n" + " ".join(assets)
            for part_number, part in enumerate(_parts(text)):
                if len(part.strip()) < 12 and not assets:
                    continue
                records.append({
                    "id": f"{parent_id}-{part_number}", "parent_id": parent_id,
                    "chapter_id": chapter, "source": source, "section": title,
                    "section_id": first["section_id"],
                    "page": first["page"],
                    "block_start": min(indices), "block_end": max(indices),
                    "kind": "text", "text": part, "asset_ids": assets,
                })
            pending.clear()

        for block in document["blocks"]:
            index = block["block_index"]
            matched_section = by_title.get(re.sub(r"\s+", "", block.get("section") or ""))
            if matched_section and matched_section["id"] != current_section["id"]:
                flush()
                current_section = matched_section
            positions[index] = current_section
            if any(start <= index <= end for start, end in exercise_ranges.get(chapter, [])):
                flush()
                continue
            if block.get("kind") == "table":
                flush()
                continue  # 表格采用已校对的 multimodal_chunks，保留表头与单元格。
            if block.get("kind") != "paragraph":
                continue
            text = str(block.get("text") or "").strip()
            if EXERCISE_HEADING.match(text):
                flush()
                continue
            assets = list(block.get("image_ids") or []) + list(block.get("formula_ids") or [])
            if not text and not assets:
                continue
            item = {"block_index": index, "section": block.get("section") or "",
                    "section_id": current_section["id"],
                    "section_title": current_section["title"], "page": current_section["page"],
                    "text": text, "asset_ids": assets}
            follows_statement = bool(
                pending and re.match(r"^(?:证(?:明)?|解)\s", text)
                and re.match(r"^(?:定理|引理|命题|推论|例)\s*\d", pending[0]["text"])
            )
            if ((UNIT_START.match(text) and not follows_statement) or assets
                    or (sum(len(p["text"]) for p in pending) + len(text) > 760
                        and not follows_statement)):
                flush()
            pending.append(item)
            if assets or len(text) >= 760:
                flush()
        flush()
        block_sections[chapter] = positions

    for filename in ("multimodal_chunks.jsonl", "vector_chunks.jsonl"):
        path = EXTRACTED / filename
        if not path.is_file():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("kind") not in {"table", "formula", "image_context"}:
                continue
            chapter = int(item["chapter_id"])
            block_index = int(item.get("block_index") or 0)
            if any(start <= block_index <= end for start, end in exercise_ranges.get(chapter, [])):
                continue
            section = block_sections[chapter].get(block_index) if "block_index" in item else None
            if section is None:
                section = next((s for s in manifests[chapter]["sections"]
                                if re.sub(r"\s+", "", s["title"]) == re.sub(r"\s+", "", item.get("section") or "")), None)
            records.append({
                "id": f"{filename}-{line_number}",
                "parent_id": (f"ch{chapter}-b{block_index}" if "block_index" in item
                              else f"{filename}-{line_number}"),
                "chapter_id": chapter, "source": item.get("source") or "",
                "section": section["title"] if section else item.get("section") or "",
                "section_id": section["id"] if section else None,
                "page": section.get("page") if section else None,
                "block_start": block_index if "block_index" in item else None,
                "block_end": block_index if "block_index" in item else None,
                "kind": item["kind"], "text": item["text"],
                "asset_ids": item.get("asset_ids") or [],
            })
    return records
