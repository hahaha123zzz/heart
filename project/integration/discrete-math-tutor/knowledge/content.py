"""教材阅读使用原 Word 的有序内容块，保留公式位置、表格单元格和绘图锚点。"""
from __future__ import annotations
import json
import re
from functools import lru_cache
from xml.etree import ElementTree as ET
from knowledge.figures import EXTRACTED_DIR, get_figure, load_figures
from knowledge.course import get_chapter
from scripts.parse_converted_textbook import NS, open_word_package, read_relationships, target_for, local_name

# Unicode 官方 Adobe Symbol 映射，保留原文件的许可声明。
SYMBOL_UNICODE = {}
for line in (EXTRACTED_DIR.parent / 'symbol_mapping.txt').read_text(encoding='utf-8').splitlines():
    if line and not line.startswith('#'):
        fields = line.split()
        if len(fields) >= 2:
            SYMBOL_UNICODE.setdefault(int(fields[1], 16), chr(int(fields[0], 16)))

def normalized(value):
    return "".join(value.split())

@lru_cache(maxsize=10)
def chapter_blocks(chapter_id: int) -> dict[int, list[dict]]:
    path = EXTRACTED_DIR / f"chapter_{chapter_id:02d}.json"
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    chapter = get_chapter(chapter_id)
    titles = {normalized(s["title"]): s["id"] for s in chapter["sections"]}
    assets = json.loads((EXTRACTED_DIR / "asset_catalog.json").read_text(encoding="utf-8"))
    by_part = {a["package_part"]: a for a in assets
               if a["chapter_id"] == chapter_id and a["kind"] in ("image", "formula")}
    approved = {f.sha256: f for f in load_figures() if f.kind == "figure"}
    positions_path = EXTRACTED_DIR / "vector_positions.json"
    positions = json.loads(positions_path.read_text(encoding="utf-8")) if positions_path.is_file() else []
    positions = [p for p in positions if p["chapter_id"] == chapter_id]
    source = EXTRACTED_DIR.parent / "imported_wordopenxml" / document["word_source"]
    out = {s["id"]: [] for s in chapter["sections"]}
    with open_word_package(source) as package:
        xml = ET.fromstring(package.read("word/document.xml"))
        body = xml.find("w:body", NS)
        relationships = read_relationships(package)
        raw_blocks = list(body)
        # 全文内存书签提供正文块位置；源文件不保存。块数不一致时拒绝错位展示。
        vectors = {}
        for position in positions:
            index = position.get('block_index')
            if position.get('body_block_count') != len(raw_blocks) or not isinstance(index, int):
                raise ValueError(f'第{chapter_id}章绘图定位与正文不一致，请重新运行 map_vector_positions.ps1')
            if 0 <= index < len(raw_blocks):
                figure = get_figure(position['id'])
                if figure:
                    vectors.setdefault(index, []).append(figure.public())

        def image_segment(node):
            rel_id = node.attrib.get(f"{{{NS['r']}}}id") or node.attrib.get(f"{{{NS['r']}}}embed")
            asset = by_part.get(target_for(rel_id or "", relationships))
            if not asset:
                return None
            figure = get_figure(asset["id"]) or approved.get(asset["sha256"])
            return {"type": figure.kind, "asset": figure.public()} if figure else None

        def segments(paragraph):
            result = []
            def visit(node):
                name = local_name(node.tag)
                if name == "txbxContent":
                    return
                if name == "sym":
                    font = node.attrib.get(f"{{{NS['w']}}}font", "")
                    value = node.attrib.get(f"{{{NS['w']}}}char", "")
                    if font in ("Symbol", "Wingdings", "Wingdings 2", "Wingdings 3", "Webdings") and re.fullmatch(r"[0-9A-Fa-f]{4}", value):
                        code = int(value, 16)
                        mapped = SYMBOL_UNICODE.get(code & 255) if font == 'Symbol' and (code < 256 or 0xF000 <= code <= 0xF0FF) else None
                        if mapped and not 0xE000 <= ord(mapped) <= 0xF8FF:
                            result.append({'type': 'text', 'text': mapped})
                        else:
                            result.append({'type': 'symbol', 'text': chr(code), 'font': font})
                    return
                if name == 'r' and node.find('w:object', NS) is None:
                    alignment = node.find('w:rPr/w:vertAlign', NS)
                    vertical = alignment.attrib.get(f"{{{NS['w']}}}val") if alignment is not None else None
                    if vertical in ('superscript', 'subscript'):
                        start = len(result)
                        for child in node:
                            visit(child)
                        parts = result[start:]
                        del result[start:]
                        result.append({'type': vertical, 'segments': parts})
                        return
                if name == "object":
                    image = node.find(".//v:imagedata", NS)
                    if image is not None:
                        segment = image_segment(image)
                        if segment:
                            shape = node.find(".//v:shape", NS)
                            style = shape.attrib.get("style", "") if shape is not None else ""
                            height = re.search(r"(?:^|;)height:([\d.]+)pt", style)
                            segment["height"] = min(160, max(18, round(float(height.group(1))*4/3))) if height else 30
                            result.append(segment)
                    return
                if name in ("imagedata", "blip"):
                    segment = image_segment(node)
                    if segment:
                        result.append(segment)
                    return
                if name in ("t", "delText") and node.text:
                    result.append({"type": "text", "text": node.text})
                elif name == "tab":
                    result.append({"type": "text", "text": " "})
                elif name in ("br", "cr"):
                    result.append({"type": "text", "text": "\n"})
                else:
                    for child in node:
                        visit(child)
            visit(paragraph)
            return result

        section_id = chapter["sections"][0]["id"]
        records = {b["block_index"]: b for b in document["blocks"]}
        for index, node in enumerate(raw_blocks):
            record = records.get(index, {})
            heading = normalized(record.get("section", ""))
            if heading in titles:
                section_id = titles[heading]
            kind = local_name(node.tag)
            if kind == "p":
                parts = segments(node)
                if any(p["type"] != "text" or p.get("text", "").strip() for p in parts):
                    out[section_id].append({"type": "paragraph", "segments": parts})
            elif kind == "tbl":
                rows = []
                for row in node.findall("w:tr", NS):
                    cells = []
                    for cell in row.findall("w:tc", NS):
                        span = cell.find("w:tcPr/w:gridSpan", NS)
                        colspan = int(span.attrib.get(f"{{{NS['w']}}}val", "1")) if span is not None else 1
                        merge = cell.find("w:tcPr/w:vMerge", NS)
                        vmerge = merge.attrib.get(f"{{{NS['w']}}}val", "continue") if merge is not None else None
                        cells.append({"paragraphs": [segments(p) for p in cell.findall("w:p", NS)],
                                      "colspan": colspan, "vmerge": vmerge})
                    rows.append(cells)
                # 将 Word 的纵向合并转成 HTML rowspan。
                active = {}
                for row in rows:
                    column = 0
                    for cell in row:
                        if cell["vmerge"] == "continue" and column in active:
                            active[column]["rowspan"] = active[column].get("rowspan", 1) + 1
                            cell["hidden"] = True
                        elif cell["vmerge"] == "restart":
                            active[column] = cell
                        else:
                            active.pop(column, None)
                        column += cell["colspan"]
                out[section_id].append({"type": "table", "rows": rows})
            for figure in vectors.get(index, []):
                out[section_id].append({"type": "image", "asset": figure})
    return out

def section_blocks(chapter_id: int, section_id: int) -> list[dict]:
    return chapter_blocks(chapter_id).get(section_id, [])
