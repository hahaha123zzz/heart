"""经核对的教材图片目录与检索。图片原件始终由服务端 ID 映射。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from knowledge.textbook import TextbookChunk, terms_for


BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "figure_assets"
CATALOG_PATH = BASE_DIR / "figure_catalog.json"
EXTRACTED_DIR = BASE_DIR / "extracted_multimodal"
EXTRACTED_CATALOG_PATH = EXTRACTED_DIR / "asset_catalog.json"
FIGURE_NUMBER = re.compile(r"图\s*(\d+)\s*[.．]\s*(\d+)")


@dataclass(frozen=True)
class Figure:
    id: str
    label: str
    chapter_id: int
    section_id: int
    source: str
    caption: str
    context: str
    path: Path
    sha256: str
    kind: str = "figure"

    def is_valid(self) -> bool:
        """读取或发送前再次验证，防止缓存后文件被替换。"""
        return self.path.is_file() and hashlib.sha256(self.path.read_bytes()).hexdigest() == self.sha256

    def public(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "caption": self.caption,
            "source": self.source,
            "chapter_id": self.chapter_id,
            "section_id": self.section_id,
            "kind": self.kind,
            "image_url": f"/api/figures/{self.id}/image",
        }


@lru_cache(maxsize=1)
def load_figures() -> tuple[Figure, ...]:
    """损坏、缺失或未审核的资产不会进入可引用目录。"""
    figures: list[Figure] = []
    seen: set[str] = set()
    asset_root = ASSET_DIR.resolve()
    if CATALOG_PATH.exists():
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        for item in catalog:
            if item.get("review_status") != "approved":
                continue
            figure_id = item.get("id", "")
            filename = item.get("filename", "")
            if not re.fullmatch(r"figure-[0-9]+-[0-9]+", figure_id) or figure_id in seen:
                continue
            if Path(filename).name != filename or Path(filename).suffix.lower() != ".png":
                continue
            path = (ASSET_DIR / filename).resolve()
            if path.parent != asset_root or not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item.get("sha256"):
                continue
            seen.add(figure_id)
            figures.append(Figure(
                id=figure_id, label=item["label"],
                chapter_id=int(item["chapter_id"]), section_id=int(item["section_id"]),
                source=item["source"], caption=item["caption"],
                context=item["context"], path=path, sha256=digest,
            ))

    if EXTRACTED_CATALOG_PATH.exists():
        catalog = json.loads(EXTRACTED_CATALOG_PATH.read_text(encoding="utf-8"))
        if isinstance(catalog, dict) and isinstance(catalog.get("value"), list):
            catalog = catalog["value"]
        vector_catalog = EXTRACTED_CATALOG_PATH.with_name("vector_catalog.json")
        if vector_catalog.is_file():
            catalog.extend(json.loads(vector_catalog.read_text(encoding="utf-8")))
        if isinstance(catalog, dict) and isinstance(catalog.get("value"), list):
            catalog = catalog["value"]
        extracted_root = (EXTRACTED_DIR / "assets").resolve()
        for item in catalog:
            if item.get("review_status") != "approved" or item.get("kind") not in ("formula", "image"):
                continue
            asset_id = item.get("id", "")
            filename = item.get("preview_filename", "")
            if not re.fullmatch(r"(?:formula|image)-[0-9]+-[0-9]+", asset_id) or asset_id in seen:
                continue
            if Path(filename).suffix.lower() != ".png":
                continue
            path = (EXTRACTED_DIR / filename).resolve()
            try:
                path.relative_to(extracted_root)
            except ValueError:
                continue
            if not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item.get("preview_sha256"):
                continue
            seen.add(asset_id)
            chapter_id = int(item["chapter_id"])
            section_id = int(item.get("section_id") or 0)
            label = f"第{chapter_id}章{'公式' if item['kind'] == 'formula' else '插图'}对象 {asset_id.rsplit('-', 1)[-1]}"
            figures.append(Figure(
                id=asset_id, label=label, chapter_id=chapter_id,
                section_id=section_id, source=item["source"],
                caption=item.get("caption") or item.get("section") or "教材对象",
                context=item.get("context") or "教材公式对象",
                path=path, sha256=digest, kind=item["kind"],
            ))
    return tuple(figures)


def get_figure(figure_id: str) -> Figure | None:
    return next((figure for figure in load_figures()
                 if figure.id == figure_id and figure.is_valid()), None)


def section_figures(chapter_id: int, section_id: int) -> list[dict]:
    return [figure.public() for figure in load_figures()
            if figure.kind == "figure" and figure.chapter_id == chapter_id
            and figure.section_id == section_id
            and figure.is_valid()]


def retrieve_figures(query: str, sources: list[TextbookChunk], limit: int = 2) -> list[Figure]:
    """明确图号优先；其余仅按图注/说明匹配，避免泛泛的“图”触发错误图片。"""
    labels = {(int(a), int(b)) for a, b in FIGURE_NUMBER.findall(query)}
    if labels:
        exact = [figure for figure in load_figures()
                if figure.kind == "figure" and figure.is_valid()
                and (figure.chapter_id, int(figure.id.rsplit("-", 1)[1])) in labels][:limit]
        if exact:
            return exact
        # 未核定图号时只跟随检索到的锚点资源，仍以对象编号显示。
    query_terms = terms_for(query)
    ranked: list[tuple[int, Figure]] = []
    source_asset_ids = {}
    for source_index, source in enumerate(sources[:1]):
        for asset_index, asset_id in enumerate(source.asset_ids):
            source_asset_ids.setdefault(asset_id, 10000 - source_index * 100 - asset_index)
    for figure in load_figures():
        if figure.id in source_asset_ids:
            if figure.is_valid():
                ranked.append((source_asset_ids[figure.id], figure))
            continue
        if figure.kind != "figure":
            continue
        if not any(Path(source.source).stem == Path(figure.source).stem
                   for source in sources):
            continue
        score = len(query_terms & terms_for(figure.caption + " " + figure.context))
        if score >= 2 and figure.is_valid():
            ranked.append((score, figure))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
    if not ranked:
        return []
    strongest = ranked[0][0]
    return [figure for score, figure in ranked if score * 2 >= strongest][:limit]


def format_figure_context(figures: list[Figure]) -> str:
    if not figures:
        return ""
    return "\n".join(
        f"[{figure.label}] {figure.caption}。教材说明：{figure.context}"
        for figure in figures
    )
