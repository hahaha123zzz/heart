"""生成教材图表候选，合并按章标注片段，并校验最终索引。

用法：
  python scripts/build_visual_index.py candidates
  python scripts/build_visual_index.py merge
  python scripts/build_visual_index.py validate
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COURSE_DIR = ROOT / "knowledge" / "courses" / "experimental-psychology-3"
RUN_DIR = ROOT / ".runtime" / "visual-index"
CANDIDATES_DIR = RUN_DIR / "candidates"
DRAFTS_DIR = RUN_DIR / "drafts"
INDEX_PATH = ROOT / "knowledge" / "course_visual_index.md"

CAPTION = re.compile(r"^\s*(图|表)\s*(\d+)\s*[-.．]\s*(\d+)\s*(.*)$")
HEADING = re.compile(
    r"^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\([一二三四五六七八九十]+\)|\d+[.．、])"
)
# 已逐张查看原件：这些尺寸在本教材中固定是栏头、二维码、装饰块或缺图占位。
DECORATIONS = {
    (809, 50): "栏头/装饰条",
    (1688, 58): "装饰横条",
    (235, 235): "二维码",
    (335, 735): "灰色装饰块",
    (400, 300): "书版小样缺图占位",
}
SIZES = {(width, height): reason for (width, height), reason in DECORATIONS.items()}


def _manifest() -> dict:
    return json.loads((COURSE_DIR / "manifest.json").read_text(encoding="utf-8"))


def _chapter_meta(chapter_id: int) -> dict:
    return next(item for item in _manifest()["chapters"] if int(item["id"]) == chapter_id)


def _chapter_dir(chapter_id: int) -> Path:
    return COURSE_DIR / "chapters" / f"chapter_{chapter_id:02d}"


def _normalize(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", text)


def _label(raw: str) -> str | None:
    match = CAPTION.match(raw)
    if not match:
        return None
    kind, chapter, number = match.group(1), match.group(2), match.group(3)
    return f"{kind}{int(chapter)}-{int(number)}"


def _captions(text: str) -> list[str]:
    result = []
    for line in text.splitlines():
        match = CAPTION.match(line)
        if not match:
            continue
        label = f"{match.group(1)}{int(match.group(2))}-{int(match.group(3))}"
        rest = re.sub(r"\s+", " ", match.group(4)).strip()
        result.append(f"{label} {rest}".strip())
    return result


def _is_heading(text: str) -> bool:
    value = text.strip()
    return bool(0 < len(value) <= 40 and HEADING.match(value)
                and not value.endswith(("。", "，", "；", "："))
                and not CAPTION.match(value))


def _pages(chapter_id: int) -> list[dict]:
    path = _chapter_dir(chapter_id) / "pdf_locations.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("pages", [])


def _page_for(pages: list[dict], text: str) -> int | None:
    needle = _normalize(text)[:60]
    if len(needle) < 6:
        return None
    for page in pages:
        if needle in _normalize(page.get("text", "")):
            return int(page["page"])
    return None


def _block_map(blocks: list[dict]) -> dict[int, dict]:
    return {int(block["block_index"]): block for block in blocks}


def _subsection(blocks: list[dict]) -> dict[int, str]:
    """block_index -> 最近的前置短标题，用于索引定位到小节。"""
    result: dict[int, str] = {}
    current = ""
    current_section = None
    for block in blocks:
        section = block.get("section_id")
        if section != current_section:
            current = ""
            current_section = section
        text = (block.get("text") or "").strip()
        if section is not None and _is_heading(text):
            current = text
        result[int(block["block_index"])] = current
    return result


def _image_row(row: dict) -> dict:
    path = _chapter_dir(int(row["chapter_id"])) / row["filename"]
    try:
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, ValueError):
        width = height = 0
    reason = SIZES.get((width, height))
    return {
        "id": row["id"],
        "path": str(path.resolve()),
        "width": width,
        "height": height,
        "existing_labels": list(row.get("labels") or []),
        "section_id": int(row.get("section_id") or 0),
        "section": row.get("section") or "",
        "block_index": int(row["block_index"]) if str(row.get("block_index", "")).isdecimal() else None,
        "context": row.get("context") or "",
        "candidate": reason is None,
        "excluded_reason": reason or "",
    }


def _image_captions(image: dict, blocks: list[dict], positions: dict[int, int]) -> list[str]:
    result = _captions(image["context"])
    position = positions.get(image["block_index"]) if image["block_index"] is not None else None
    if position is not None:
        for block in blocks[max(0, position - 5):position + 6]:
            result.extend(_captions(block.get("text") or ""))
    result.extend(image["existing_labels"])
    seen = []
    for item in result:
        value = item.strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _table_groups(blocks: list[dict], positions: dict[int, int]) -> list[dict]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for block in blocks:
        if block.get("kind") != "table" or block.get("section_id") is None:
            continue
        position = positions[int(block["block_index"])]
        if current:
            previous = current[-1]
            between = blocks[positions[int(previous["block_index"])] + 1:position]
            same_section = previous.get("section_id") == block.get("section_id")
            close = position - positions[int(previous["block_index"])] <= 4
            new_caption = any(_label(line) for item in between
                              for line in (item.get("text") or "").splitlines())
            if same_section and close and not new_caption and not any(
                    _is_heading(item.get("text") or "") for item in between):
                current.append(block)
                continue
            groups.append(current)
        current = [block]
    if current:
        groups.append(current)
    return groups


def _table_caption(group: list[dict], blocks: list[dict],
                   positions: dict[int, int]) -> tuple[str, str]:
    for block in group:
        for line in (block.get("text") or "").splitlines():
            if _label(line):
                return line.strip(), "table"
    start = positions[int(group[0]["block_index"])]
    for offset in range(1, 7):
        if start - offset < 0:
            break
        text = (blocks[start - offset].get("text") or "").strip()
        if _label(text):
            return text, "before"
    return "", ""


def _table_row(group: list[dict], blocks: list[dict], positions: dict[int, int],
               subsection: dict[int, str], pages: list[dict]) -> dict:
    text = "\n".join(block.get("text") or "" for block in group).strip()
    caption, caption_source = _table_caption(group, blocks, positions)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    label = _label(caption) if caption else None
    return {
        "blocks": [int(block["block_index"]) for block in group],
        "section_id": int(group[0].get("section_id") or 0),
        "section": group[0].get("section") or "",
        "subsection": subsection.get(int(group[0]["block_index"]), ""),
        "caption": caption,
        "caption_label": label or "",
        "caption_source": caption_source,
        "text": text,
        "first_lines": lines[:12],
        "page": _page_for(pages, caption if caption else (lines[0] if lines else "")),
    }


def chapter_candidates(chapter_id: int) -> dict:
    meta = _chapter_meta(chapter_id)
    document = json.loads((_chapter_dir(chapter_id) / "document.json").read_text(encoding="utf-8"))
    blocks = document["blocks"]
    positions = {int(block["block_index"]): index for index, block in enumerate(blocks)}
    subsections = _subsection(blocks)
    pages = _pages(chapter_id)
    rows = json.loads((_chapter_dir(chapter_id) / "assets.json").read_text(encoding="utf-8"))

    images = []
    for row in rows:
        image = _image_row(row)
        captions = _image_captions(image, blocks, positions)
        image["caption_candidates"] = captions
        image["caption"] = captions[0] if captions else ""
        image["subsection"] = subsections.get(image["block_index"], "") if image["block_index"] is not None else ""
        image["page"] = _page_for(pages, image["caption"]) if image["caption"] else None
        images.append(image)

    groups = _table_groups(blocks, positions)
    tables = []
    for group in groups:
        row = _table_row(group, blocks, positions, subsections, pages)
        text = row["text"]
        if len(text) < 40 and not re.search(r"\d", text):
            continue
        tables.append(row)

    return {
        "chapter_id": chapter_id,
        "title": meta["title"],
        "sections": [{"id": int(section["id"]), "title": section["title"]}
                     for section in meta["sections"]],
        "images": images,
        "tables": tables,
        "stats": {
            "images": len(images),
            "candidate_images": sum(1 for image in images if image["candidate"]),
            "excluded_images": sum(1 for image in images if not image["candidate"]),
            "tables": len(tables),
        },
    }


def write_candidates(out_dir: Path = CANDIDATES_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for chapter_id in range(1, 12):
        data = chapter_candidates(chapter_id)
        path = out_dir / f"chapter_{chapter_id:02d}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(path)
    return written


def _draft_lines(drafts_dir: Path, chapter_id: int) -> list[str]:
    path = drafts_dir / f"chapter_{chapter_id:02d}.md"
    if not path.is_file():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            continue
        if line.strip():
            lines.append(line.rstrip())
    return lines


def merge_drafts(drafts_dir: Path = DRAFTS_DIR, out_path: Path = INDEX_PATH) -> dict:
    from knowledge.visual_index import number_from_text, parse_index

    manifest = _manifest()
    heading = re.compile(r"^###\s*第\s*(\d+|[一二三四五六七八九十]+)\s*节\s*(.*)$")

    def title(raw: str) -> str:
        return re.sub(r"^第\s*(?:\d+|[一二三四五六七八九十]+)\s*节\s*", "", raw).strip()

    parts = ["# 实验心理学（第3版）图表索引",
             "> course_id: experimental-psychology-3 ｜ 教材版本: " + str(manifest.get("archive_sha256", ""))[:12]]
    for chapter in manifest["chapters"]:
        chapter_id = int(chapter["id"])
        parts += ["", f"## 第{chapter_id}章 {chapter['title']}"]
        known = {int(section["id"]) for section in chapter["sections"]}
        sections: dict[int, list[str]] = {}
        current = None
        for line in _draft_lines(drafts_dir, chapter_id):
            match = heading.match(line)
            if match:
                current = number_from_text(match.group(1))
                if current not in known:
                    raise ValueError(f"第{chapter_id}章出现未知小节 {current}")
                sections.setdefault(current, [])
                continue
            if current is None:
                if line.startswith("- "):
                    raise ValueError(f"第{chapter_id}章有条目不在任何小节下")
                continue
            sections[current].append(line)
        for section in chapter["sections"]:
            section_id = int(section["id"])
            parts += ["", f"### 第{section_id}节 {title(section['title'])}"]
            body = sections.get(section_id, [])
            while body and not body[-1].strip():
                body.pop()
            parts += body
    text = "\n".join(parts).rstrip() + "\n"
    parsed = parse_index(text)
    counts = collections.Counter(entry.status for entry in parsed.entries)
    header = [parts[0],
              f"> course_id: experimental-psychology-3 ｜ 条目: {len(parsed.entries)} ｜ "
              f"已核对: {counts.get('已核对', 0)} ｜ 待核: {counts.get('待核', 0)} ｜ "
              f"缺图: {counts.get('缺图', 0)}"]
    text = "\n".join(header + parts[2:]).rstrip() + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return {"entries": len(parsed.entries), "status": dict(counts), "path": str(out_path)}


def _all_assets() -> dict[str, dict]:
    result = {}
    for chapter_id in range(1, 12):
        rows = json.loads((_chapter_dir(chapter_id) / "assets.json").read_text(encoding="utf-8"))
        for row in rows:
            image = _image_row(row)
            result[image["id"]] = image
    return result


def _all_blocks() -> dict[int, set[int]]:
    result = {}
    for chapter_id in range(1, 12):
        document = json.loads((_chapter_dir(chapter_id) / "document.json").read_text(encoding="utf-8"))
        result[chapter_id] = {int(block["block_index"]) for block in document["blocks"]}
    return result


def validate_index(path: Path = INDEX_PATH) -> dict:
    from knowledge.visual_index import parse_index

    text = path.read_text(encoding="utf-8")
    parsed = parse_index(text)
    errors = []
    chapters = {entry.chapter_id for entry in parsed.entries}
    if chapters != set(range(1, 12)):
        errors.append(f"章节覆盖不完整: {sorted(chapters)}")
    assets = _all_assets()
    blocks = _all_blocks()
    seen = set()
    for entry in parsed.entries:
        if not entry.type or not entry.name or not entry.knowledge_points or not entry.content or not entry.use_for:
            errors.append(f"{entry.label}: 字段不完整")
        if entry.status not in ("已核对", "待核", "缺图"):
            errors.append(f"{entry.label}: 状态非法 {entry.status}")
        if (entry.chapter_id, entry.label) in seen:
            errors.append(f"{entry.label}: 重复编号")
        seen.add((entry.chapter_id, entry.label))
        if entry.asset_id:
            asset = assets.get(entry.asset_id)
            if asset is None:
                errors.append(f"{entry.label}: asset_id 不存在 {entry.asset_id}")
            elif not asset["candidate"]:
                errors.append(f"{entry.label}: asset_id 是装饰/占位 {entry.asset_id}")
        if entry.blocks:
            missing = set(entry.blocks) - blocks.get(entry.chapter_id, set())
            if missing:
                errors.append(f"{entry.label}: blocks 不存在 {sorted(missing)}")
        if entry.status == "缺图" and entry.asset_id:
            errors.append(f"{entry.label}: 缺图条目不能带 asset_id")
    caption = re.compile(r"^(图|表)\s*(\d+)\s*[-.．]\s*(\d+)\s")
    missing_captions = set()
    for chapter_id in range(1, 12):
        document = json.loads((_chapter_dir(chapter_id) / "document.json").read_text(encoding="utf-8"))
        for block in document["blocks"]:
            for line in (block.get("text") or "").splitlines():
                match = caption.match(line.strip())
                if not match:
                    continue
                label = f"{match.group(1)}{int(match.group(2))}-{int(match.group(3))}"
                if (chapter_id, label) not in seen:
                    missing_captions.add((chapter_id, label))
    for chapter_id, label in sorted(missing_captions):
        errors.append(f"{label}: 教材有图注但索引缺失（第{chapter_id}章）")
    return {"chapters": len(chapters), "entries": len(parsed.entries),
            "errors": errors, "status": dict(collections.Counter(entry.status for entry in parsed.entries))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("candidates", "merge", "validate"))
    args = parser.parse_args()
    if args.command == "candidates":
        for path in write_candidates():
            data = json.loads(path.read_text(encoding="utf-8"))
            print(path.name, data["stats"])
    elif args.command == "merge":
        print(json.dumps(merge_drafts(), ensure_ascii=False))
    else:
        print(json.dumps(validate_index(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
