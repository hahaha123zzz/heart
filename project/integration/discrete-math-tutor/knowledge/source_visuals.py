"""Original textbook visual assets, bound to the published chapter/version.

The psychology course keeps Word/PDF-extracted images and formula objects in
``knowledge/courses/experimental-psychology-3/chapters/<chapter>/assets.json``.
This module is the read-only adapter between those files and the existing
``knowledge.figures``/PDF crop interfaces. It never generates images and never
treats an unverifiable file as a source.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is present in the project runtime
    Image = None

from knowledge.course_config import PSYCHOLOGY_DIR

# 已逐种查看原件字节；只排除装饰，不用尺寸推断真实实验图一定缺失。
DECORATIONS = {
    'f4c0857a987cb18d93fe16d4e485a11225a61a5437b303af0e196e71d5803c3e': '扫码入口（已查看原件，不是实验图5-7）',
    '4250a56e71376f1b1942e48441304918a374f701f1e95c8423719ddf8b333b6f': '拓展阅读装饰横条',
    'f7d9231730c647ca17e962e662288f568a799620b081137f212dbc3f660f971c': '概念术语栏头',
    '02214750659c0c3f157cf0973b6d38797bbe94204a75cdcd487ed9daf1e19972': '本章重点栏头',
    'b930fe5d39fe05ccd1fdc04fac54044b5d6accb27d921b4319e2959c0b76b5b2': '推荐阅读栏头',
}


@dataclass(frozen=True)
class SourceVisual:
    id: str
    chapter_id: int
    section_id: int
    block_index: int | None
    kind: str
    path: Path
    sha256: str
    source: str
    source_sha256: str
    labels: tuple[str, ...]
    context: str
    section: str
    review_status: str
    occurrences: tuple[int, ...] = ()

    def is_valid(self) -> bool:
        try:
            manifest = json.loads((PSYCHOLOGY_DIR / 'manifest.json').read_bytes())
            source = next(item for item in manifest['full_import']['chapters']
                          if item['chapter_id'] == self.chapter_id)
            original = (PSYCHOLOGY_DIR / source['docx']).resolve()
            if (not original.is_relative_to(PSYCHOLOGY_DIR.resolve()) or
                    source['source_sha256'] != self.source_sha256 or
                    _sha256(original) != self.source_sha256):
                return False
            # 缓存中的位置不能继续用于已重排的小节或已替换的资产登记。
            current = next(item for item in json.loads((_chapter_dir(self.chapter_id) / 'assets.json').read_bytes())
                           if item['id'] == self.id)
            return (current.get('section_id') == self.section_id and current.get('block_index') == self.block_index
                and tuple(item['block'] for item in current.get('occurrences', [])) == self.occurrences
                and tuple(current.get('labels') or ()) == self.labels
                and current.get('review_status', 'pending') == self.review_status
                and current.get('kind') == self.kind
                and current.get('source_sha256') == self.source_sha256
                and current.get('sha256') == self.sha256
                and (_chapter_dir(self.chapter_id) / current['filename']).resolve() == self.path.resolve()
                and self.path.is_file() and _sha256(self.path) == self.sha256)
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            return False

    def public(self) -> dict:
        return {
            "id": self.id,
            "label": self.labels[0] if self.labels else f"第{self.chapter_id}章教材原图",
            "caption": self.labels[0] if self.labels else (self.section or "教材原图"),
            "source": self.source,
            "chapter_id": self.chapter_id,
            "section_id": self.section_id,
            "block_index": self.block_index,
            "kind": self.kind,
            "review_status": self.review_status,
            "image_url": f"/api/figures/{self.id}/image",
        }


@dataclass(frozen=True)
class VisualGap:
    chapter_id: int
    visual_id: str
    reason: str
    classification: str = 'unresolved'

    def public(self) -> dict:
        return {"chapter_id": self.chapter_id, "visual_id": self.visual_id, "reason": self.reason,
                "classification": self.classification}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _manifest() -> dict:
    path = PSYCHOLOGY_DIR / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _expected_source_hashes() -> dict[int, str]:
    manifest = _manifest()
    result = {}
    for chapter in manifest.get("full_import", {}).get("chapters", []):
        try:
            result[int(chapter["chapter_id"])] = str(chapter["source_sha256"])
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _chapter_dir(chapter_id: int) -> Path:
    return PSYCHOLOGY_DIR / "chapters" / f"chapter_{chapter_id:02d}"


def _load_chapter(chapter_id: int):
    visuals: list[SourceVisual] = []
    gaps: list[VisualGap] = []
    chapter_dir = _chapter_dir(chapter_id)
    path = chapter_dir / "assets.json"
    if not path.is_file():
        return visuals, gaps
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        gaps.append(VisualGap(chapter_id, "", f"assets.json 无法读取：{type(exc).__name__}"))
        return visuals, gaps
    if not isinstance(rows, list):
        gaps.append(VisualGap(chapter_id, "", "assets.json 顶层不是数组"))
        return visuals, gaps
    expected_source = _expected_source_hashes().get(chapter_id)
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        visual_id = str(item.get("id") or "")
        kind = str(item.get("kind") or "")
        if not visual_id or visual_id in seen or kind not in ("image", "formula"):
            continue
        seen.add(visual_id)
        filename = str(item.get("filename") or "")
        relative = Path(filename)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            gaps.append(VisualGap(chapter_id, visual_id, "资源路径不在章节目录内或类型不支持"))
            continue
        file_path = (chapter_dir / relative).resolve()
        try:
            file_path.relative_to(chapter_dir.resolve())
        except ValueError:
            gaps.append(VisualGap(chapter_id, visual_id, "资源路径越出章节目录"))
            continue
        if not file_path.is_file():
            gaps.append(VisualGap(chapter_id, visual_id, "原图文件缺失"))
            continue
        digest = _sha256(file_path)
        if digest != str(item.get("sha256") or ""):
            gaps.append(VisualGap(chapter_id, visual_id, "原图哈希与登记不一致"))
            continue
        if digest in DECORATIONS:
            gaps.append(VisualGap(chapter_id, visual_id,
                                  f'非知识图：{DECORATIONS[digest]}，不作为知识证据', 'decoration'))
            continue
        source_sha = str(item.get("source_sha256") or "")
        if expected_source and source_sha != expected_source:
            gaps.append(VisualGap(chapter_id, visual_id, "原教材源文件哈希与当前发布清单不一致"))
            continue
        if kind == "image" and Image is not None:
            try:
                with Image.open(file_path) as image:
                    width, height = image.size
            except (OSError, ValueError):
                gaps.append(VisualGap(chapter_id, visual_id, "原图无法读取"))
                continue
            # 尺寸异常只负责过滤；能确认的装饰和不能确认的缺口分别登记。
            if height < 80 or (height and width / height > 12):
                decoration = DECORATIONS.get(digest)
                gaps.append(VisualGap(chapter_id, visual_id,
                    f'装饰性栏头：{decoration}，不作为知识证据' if decoration else '占位/缺图资产尺寸异常，不作为教材原图',
                    'decoration' if decoration else 'unresolved'))
                continue
        occurrences = tuple(int(value.get("block")) for value in item.get("occurrences") or []
                            if isinstance(value, dict) and isinstance(value.get("block"), (int, str))
                            and str(value.get("block")).isdecimal())
        visuals.append(SourceVisual(
            id=visual_id, chapter_id=chapter_id,
            section_id=int(item.get("section_id") or 0),
            block_index=int(item["block_index"]) if str(item.get("block_index", "")).isdecimal() else None,
            kind=kind, path=file_path, sha256=digest,
            source=str(item.get("source") or ""), source_sha256=source_sha,
            labels=tuple(str(label) for label in item.get("labels") or () if str(label).strip()),
            context=str(item.get("context") or ""), section=str(item.get("section") or ""),
            review_status=str(item.get("review_status") or "pending"),
            occurrences=occurrences,
        ))
    return visuals, gaps


@lru_cache(maxsize=1)
def load_visuals():
    visuals: list[SourceVisual] = []
    gaps: list[VisualGap] = []
    for chapter_id in range(1, 12):
        chapter_visuals, chapter_gaps = _load_chapter(chapter_id)
        visuals.extend(chapter_visuals)
        gaps.extend(chapter_gaps)
    return tuple(visuals), tuple(gaps)


def clear_cache():
    load_visuals.cache_clear()
    _manifest.cache_clear()


def get_visual(visual_id: str) -> SourceVisual | None:
    return next((visual for visual in load_visuals()[0]
                 if visual.id == visual_id and visual.is_valid()), None)


def visuals_for_section(chapter_id: int, section_id: int) -> list[SourceVisual]:
    return [visual for visual in load_visuals()[0]
            if visual.chapter_id == chapter_id and visual.section_id == section_id and visual.is_valid()]


def visuals_for_block(chapter_id: int, block_index: int) -> list[SourceVisual]:
    return [visual for visual in load_visuals()[0]
            if visual.chapter_id == chapter_id and visual.is_valid()
            and (visual.block_index == block_index or block_index in visual.occurrences)]


def gaps() -> list[dict]:
    return [gap.public() for gap in load_visuals()[1]]


def stats() -> dict:
    visuals, gaps = load_visuals()
    by_chapter: dict[int, int] = {}
    for visual in visuals:
        by_chapter[visual.chapter_id] = by_chapter.get(visual.chapter_id, 0) + 1
    return {"total": len(visuals), "by_chapter": by_chapter,
            "pending_review": sum(1 for visual in visuals if visual.review_status != "approved"),
            "gaps": len(gaps),
            "filtered_decorations": sum(gap.classification == 'decoration' for gap in gaps),
            "unresolved_gaps": sum(gap.classification != 'decoration' for gap in gaps)}
