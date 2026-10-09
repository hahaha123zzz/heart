"""解析 Word 转换后的教材，导出表格、公式、图片及其邻近文字。

输入为 convert_legacy_docs.ps1 产生的 Flat OPC。仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "o": "urn:schemas-microsoft-com:office:office",
    "v": "urn:schemas-microsoft-com:vml",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}
CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
PKG_NS = "http://schemas.microsoft.com/office/2006/xmlPackage"
HEADING_RE = re.compile(r"^\d+(?:\.\d+){1,3}\s*[^\s].{0,100}$")
FIGURE_RE = re.compile(r"图\s*\d+\s*[.．]\s*\d+")
TABLE_RE = re.compile(r"表\s*\d+\s*[.．-]\s*\d+")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def paragraph_text(node: ET.Element) -> str:
    parts: list[str] = []
    for element in node.iter():
        name = local_name(element.tag)
        if name in ("t", "delText") and element.text:
            parts.append(element.text)
        elif name == "tab":
            parts.append("\t")
        elif name in ("br", "cr"):
            parts.append("\n")
    return "".join(parts).strip()


def target_for(rel_id: str, relationships: dict[str, str]) -> str | None:
    target = relationships.get(rel_id)
    if not target:
        return None
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("word", target))


def read_relationships(package: zipfile.ZipFile) -> dict[str, str]:
    try:
        root = ET.fromstring(package.read("word/_rels/document.xml.rels"))
    except KeyError:
        return {}
    return {
        item.attrib.get("Id", ""): item.attrib.get("Target", "")
        for item in root.findall("rel:Relationship", NS)
        if item.attrib.get("TargetMode") != "External"
    }


def open_word_package(path: Path) -> zipfile.ZipFile:
    """把 Word.Document.WordOpenXML 返回的 Flat OPC 还原成可读的包。"""
    if not path.name.endswith(".flatopc.xml"):
        return zipfile.ZipFile(path)
    root = ET.fromstring(path.read_bytes())
    namespace = {"pkg": PKG_NS}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for part in root.findall("pkg:part", namespace):
            name = part.attrib.get(f"{{{PKG_NS}}}name", "").lstrip("/")
            if not name:
                continue
            xml_data = part.find("pkg:xmlData", namespace)
            binary_data = part.find("pkg:binaryData", namespace)
            if xml_data is not None and list(xml_data):
                content = ET.tostring(list(xml_data)[0], encoding="utf-8", xml_declaration=True)
            elif binary_data is not None:
                encoded = "".join((binary_data.text or "").split())
                content = base64.b64decode(encoded)
            else:
                content = b""
            package.writestr(name, content)
    buffer.seek(0)
    return zipfile.ZipFile(buffer, "r")


def block_paragraphs(block: ET.Element) -> list[ET.Element]:
    if local_name(block.tag) == "p":
        return [block]
    return block.findall(".//w:p", NS)


def heading_section(text: str, current: str) -> str:
    value = " ".join(text.split())
    return value if HEADING_RE.match(value) else current


def parse_document(path: Path, source_txt: str, asset_root: Path) -> tuple[dict, list[dict], list[dict]]:
    match = CHAPTER_RE.search(path.stem)
    if not match:
        raise ValueError(f"无法从文件名识别章节：{path.name}")
    chapter_id = int(match.group(1))
    sha_source = hashlib.sha256(path.read_bytes()).hexdigest()
    chapter_assets = asset_root / f"chapter_{chapter_id:02d}"
    chapter_assets.mkdir(parents=True, exist_ok=True)
    assets: list[dict] = []
    chunks: list[dict] = []
    blocks_out: list[dict] = []
    asset_by_target: dict[tuple[str, str], dict] = {}
    asset_counter = {"image": 0, "formula": 0, "ole": 0}

    with open_word_package(path) as package:
        root = ET.fromstring(package.read("word/document.xml"))
        body = root.find("w:body", NS)
        if body is None:
            raise ValueError(f"DOCX 缺少 document body：{path.name}")
        relationships = read_relationships(package)

        def register(target: str | None, kind: str, block_index: int,
                     paragraph_index: int, prog_id: str = "") -> str | None:
            if target is None or target not in package.namelist():
                return None
            key = (kind, target)
            if key in asset_by_target:
                asset = asset_by_target[key]
                asset["occurrences"].append({"block": block_index, "paragraph": paragraph_index})
                return asset["id"]
            asset_counter[kind] += 1
            suffix = Path(target).suffix.lower() or ".bin"
            asset_id = f"{kind}-{chapter_id:02d}-{asset_counter[kind]:04d}"
            digest = hashlib.sha256(package.read(target)).hexdigest()
            filename = f"{asset_id}{suffix}"
            output = chapter_assets / filename
            output.write_bytes(package.read(target))
            asset = {
                "id": asset_id,
                "kind": kind,
                "chapter_id": chapter_id,
                "source": source_txt,
                "word_source": path.name,
                "source_sha256": sha_source,
                "package_part": target,
                "filename": str(output.relative_to(asset_root.parent)).replace("\\", "/"),
                "extension": suffix,
                "sha256": digest,
                "prog_id": prog_id,
                "block_index": block_index,
                "paragraph_index": paragraph_index,
                "occurrences": [{"block": block_index, "paragraph": paragraph_index}],
                "review_status": (
                    "approved" if kind == "formula" and
                    ("equation" in prog_id.casefold() or "mathtype" in prog_id.casefold())
                    else "pending"
                ),
            }
            assets.append(asset)
            asset_by_target[key] = asset
            return asset_id

        def paragraph_assets(paragraph: ET.Element, block_index: int,
                             paragraph_index: int) -> tuple[list[str], list[str]]:
            image_ids: list[str] = []
            formula_ids: list[str] = []
            object_nodes = paragraph.findall(".//w:object", NS)
            object_image_refs: set[str] = set()
            for obj in object_nodes:
                ole = obj.find(".//o:OLEObject", NS)
                prog_id = ole.attrib.get("ProgID", "") if ole is not None else ""
                is_formula = "equation" in prog_id.casefold() or "mathtype" in prog_id.casefold()
                image_refs = [item.attrib.get(f"{{{NS['r']}}}id", "")
                               for item in obj.findall(".//v:imagedata", NS)]
                object_image_refs.update(ref for ref in image_refs if ref)
                for rel_id in image_refs:
                    asset_id = register(target_for(rel_id, relationships),
                                        "formula" if is_formula else "image",
                                        block_index, paragraph_index, prog_id)
                    if asset_id:
                        (formula_ids if is_formula else image_ids).append(asset_id)
                if ole is not None:
                    rel_id = ole.attrib.get(f"{{{NS['r']}}}id", "")
                    target = target_for(rel_id, relationships)
                    if target and target in package.namelist():
                        register(target, "ole", block_index, paragraph_index, prog_id)

            for image_node in paragraph.findall(".//v:imagedata", NS):
                rel_id = image_node.attrib.get(f"{{{NS['r']}}}id", "")
                if not rel_id or rel_id in object_image_refs:
                    continue
                asset_id = register(target_for(rel_id, relationships), "image",
                                    block_index, paragraph_index)
                if asset_id:
                    image_ids.append(asset_id)
            for image_node in paragraph.findall(".//a:blip", NS):
                rel_id = image_node.attrib.get(f"{{{NS['r']}}}embed", "")
                asset_id = register(target_for(rel_id, relationships), "image",
                                    block_index, paragraph_index)
                if asset_id:
                    image_ids.append(asset_id)
            return list(dict.fromkeys(image_ids)), list(dict.fromkeys(formula_ids))

        current_section = path.stem
        for block_index, block in enumerate(list(body)):
            block_kind = local_name(block.tag)
            paragraphs = block_paragraphs(block)
            paragraph_records: list[dict] = []
            all_image_ids: list[str] = []
            all_formula_ids: list[str] = []
            for paragraph_index, paragraph in enumerate(paragraphs):
                text = paragraph_text(paragraph)
                image_ids, formula_ids = paragraph_assets(
                    paragraph, block_index, paragraph_index
                )
                all_image_ids.extend(image_ids)
                all_formula_ids.extend(formula_ids)
                if text:
                    current_section = heading_section(text, current_section)
                paragraph_records.append({
                    "text": text,
                    "image_ids": image_ids,
                    "formula_ids": formula_ids,
                })

            text = "\n".join(row["text"] for row in paragraph_records if row["text"])
            record = {
                "block_index": block_index,
                "kind": "table" if block_kind == "tbl" else "paragraph" if block_kind == "p" else block_kind,
                "section": current_section,
                "text": text,
                "paragraphs": paragraph_records,
                "image_ids": list(dict.fromkeys(all_image_ids)),
                "formula_ids": list(dict.fromkeys(all_formula_ids)),
            }

            if block_kind == "tbl":
                rows: list[list[str]] = []
                for row in block.findall("w:tr", NS):
                    cells = []
                    for cell in row.findall("w:tc", NS):
                        cells.append(" / ".join(
                            paragraph_text(p) for p in cell.findall(".//w:p", NS)
                            if paragraph_text(p)
                        ))
                    if any(cells):
                        rows.append(cells)
                record["rows"] = rows
                width = max((len(row) for row in rows), default=0)
                table_text = "\n".join(
                    "| " + " | ".join(row + [""] * (width - len(row))) + " |"
                    for row in rows
                )
                if table_text:
                    chunks.append({
                        "kind": "table", "chapter_id": chapter_id,
                        "source": source_txt, "section": current_section,
                        "text": f"教材表格\n{table_text}",
                        "asset_ids": list(dict.fromkeys(all_formula_ids + all_image_ids)),
                        "block_index": block_index,
                    })
            if all_formula_ids:
                chunks.append({
                    "kind": "formula", "chapter_id": chapter_id,
                    "source": source_txt, "section": current_section,
                    "text": text or "教材公式（以原公式图像为准）",
                    "asset_ids": list(dict.fromkeys(all_formula_ids)),
                    "block_index": block_index,
                })
            if all_image_ids:
                chunks.append({
                    "kind": "image_context", "chapter_id": chapter_id,
                    "source": source_txt, "section": current_section,
                    "text": text or "教材图片",
                    "asset_ids": list(dict.fromkeys(all_image_ids)),
                    "block_index": block_index,
                })
            blocks_out.append(record)

    # 将紧邻图注和正文归到图片资产，供生成待审核目录与检索上下文使用。
    try:
        from knowledge.course import get_chapter

        course_sections = get_chapter(chapter_id)["sections"]
    except (ImportError, TypeError, KeyError):
        course_sections = []
    section_lookup = {
        "".join(item["title"].split()): item["id"]
        for item in course_sections
    }

    def section_id_for(title: str) -> int | None:
        normalized = "".join(title.split())
        return section_lookup.get(normalized)

    for block in blocks_out:
        block["section_id"] = section_id_for(block["section"])
    for chunk in chunks:
        chunk["section_id"] = section_id_for(chunk["section"])
        index = chunk["block_index"]
        adjacent = blocks_out[max(0, index - 3):min(len(blocks_out), index + 3)]
        previous = "\n".join(item["text"] for item in adjacent if item["text"] and item["block_index"] < index)
        following = "\n".join(item["text"] for item in adjacent if item["text"] and item["block_index"] > index)
        if chunk["kind"] == "formula":
            parts = ["公式所在段落：" + (chunk["text"] or "原公式见随附图片。")]
            if previous:
                parts.append("公式前文（仅提供背景）：\n" + previous[-600:])
            if following:
                parts.append("公式后文（可能是后续定理或推导，不代表该公式的编号）：\n" + following[:600])
            chunk["text"] = "\n".join(parts)
        else:
            context = "\n".join(part for part in (previous[-600:], following[:600]) if part)
            if context:
                chunk["text"] += "\n邻近正文：\n" + context

    for asset in assets:
        if asset["kind"] not in ("image", "formula"):
            continue
        index = asset["block_index"]
        adjacent = blocks_out[max(0, index - 2): min(len(blocks_out), index + 3)]
        nearby_text = "\n".join(item["text"] for item in adjacent if item["text"])
        figure_labels = FIGURE_RE.findall(nearby_text)
        table_labels = TABLE_RE.findall(nearby_text)
        asset["labels"] = list(dict.fromkeys(figure_labels + table_labels))
        asset["section"] = blocks_out[index]["section"] if index < len(blocks_out) else path.stem
        asset["section_id"] = section_id_for(asset["section"])
        asset["context"] = nearby_text[:1800]
        if asset["kind"] != "formula":
            asset["review_status"] = "pending"

    document = {
        "chapter_id": chapter_id,
        "source": source_txt,
        "word_source": path.name,
        "docx_sha256": sha_source,
        "block_count": len(blocks_out),
        "assets": assets,
        "blocks": blocks_out,
    }
    return document, chunks, assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "knowledge" / "imported_wordopenxml")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "knowledge" / "extracted_multimodal")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    assets_root = args.output / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    sources = {}
    text_dir = Path(__file__).resolve().parents[1] / "knowledge" / "textbook_text"
    for text_path in text_dir.glob("*.txt"):
        match = CHAPTER_RE.search(text_path.stem)
        if match:
            sources[int(match.group(1))] = text_path.name

    all_chunks: list[dict] = []
    all_assets: list[dict] = []
    summary: list[dict] = []
    for word_file in sorted(args.input.glob("*.flatopc.xml")):
        document, chunks, assets = parse_document(
            word_file, sources.get(int(CHAPTER_RE.search(word_file.stem).group(1)), word_file.stem + ".txt"),
            assets_root,
        )
        chapter_id = document["chapter_id"]
        output_doc = args.output / f"chapter_{chapter_id:02d}.json"
        output_doc.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        all_chunks.extend(chunks)
        all_assets.extend(assets)
        summary.append({
            "chapter_id": chapter_id,
            "source": document["source"],
            "blocks": document["block_count"],
            "tables": sum(block["kind"] == "table" for block in document["blocks"]),
            "formula_objects": sum(bool(block["formula_ids"]) for block in document["blocks"]),
            "images": sum(bool(block["image_ids"]) for block in document["blocks"]),
            "assets": len(assets),
        })
    (args.output / "multimodal_chunks.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in all_chunks),
        encoding="utf-8",
    )
    (args.output / "asset_catalog.json").write_text(
        json.dumps(all_assets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
