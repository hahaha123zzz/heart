"""Read-only course release/version binding for citations and assets.

The manifest records the intended course edition while chapter documents, PDFs,
visual assets and the retrieval index each carry their own hashes. This module
combines them into one release identity without publishing, rewriting or
re-indexing anything. ``ready`` is conservative: the current staging manifest
is reported as not ready even when all local files exist.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

from knowledge.course_config import PSYCHOLOGY_DIR
from knowledge.pdf_reader import document_for_chapter, pdf_path


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _manifest() -> dict:
    path = PSYCHOLOGY_DIR / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def chapter_source_identity(chapter_id, manifest, assets):
    directory = PSYCHOLOGY_DIR / 'chapters' / f'chapter_{chapter_id:02d}'
    source = next((item for item in manifest.get('full_import', {}).get('chapters', [])
                   if item['chapter_id'] == chapter_id), {})
    paths = [(PSYCHOLOGY_DIR / source['docx'], source.get('source_sha256'))] if source.get('docx') else []
    paths += [(directory / item['filename'], item.get('sha256')) for item in json.loads(assets)]
    actual = []
    for path, expected in paths:
        # 版本核验不能越出本课程目录，也不能把缺失文件当成原版本。
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if (
            path.resolve().is_relative_to(PSYCHOLOGY_DIR.resolve()) and path.is_file()) else None
        actual.append((str(path.relative_to(PSYCHOLOGY_DIR)), expected, digest))
    return hashlib.sha256(json.dumps(actual, ensure_ascii=False).encode()).hexdigest(), (
        bool(source.get('docx')) and bool(actual) and bool(actual[0][1]) and actual[0][1] == actual[0][2])


@lru_cache(maxsize=1)
def snapshot() -> dict:
    manifest = _manifest()
    course_id = manifest.get("course_id") or PSYCHOLOGY_DIR.name
    chapters = []
    gaps = []
    for chapter in manifest.get("chapters", []):
        try:
            chapter_id = int(chapter["id"])
        except (KeyError, TypeError, ValueError):
            continue
        directory = PSYCHOLOGY_DIR / "chapters" / f"chapter_{chapter_id:02d}"
        document_path = directory / "document.json"
        assets_path = directory / "assets.json"
        document_sha = _sha256(document_path)
        assets_sha = _sha256(assets_path)
        source_version, source_valid = chapter_source_identity(chapter_id, manifest, assets_path.read_bytes()) if assets_sha else (None, False)
        if not source_valid:
            gaps.append(f"第{chapter_id}章原始源文件缺失或哈希变化")
        record = document_for_chapter(chapter_id)
        pdf_sha = _sha256(pdf_path(record)) if record else None
        declared_pdf = record.get("version") if record else None
        if not document_sha:
            gaps.append(f"第{chapter_id}章 document.json 缺失")
        if not pdf_sha:
            gaps.append(f"第{chapter_id}章 PDF 缺失")
        elif declared_pdf and pdf_sha != declared_pdf:
            gaps.append(f"第{chapter_id}章 PDF 与发布版本不一致")
        if not assets_sha:
            gaps.append(f"第{chapter_id}章 assets.json 缺失")
        chapters.append({
            "chapter_id": chapter_id,
            "document_sha256": document_sha,
            "document_version": declared_pdf,
            "pdf_sha256": pdf_sha,
            "assets_sha256": assets_sha,
            "source_version": source_version,
        })
    index_path = PSYCHOLOGY_DIR / "rag_index.sqlite3"
    index_sha = _sha256(index_path)
    if not index_sha:
        gaps.append("检索索引 rag_index.sqlite3 缺失")
    try:
        from knowledge.source_visuals import stats as visual_stats
        visuals = visual_stats()
    except Exception:
        visuals = {"total": 0, "by_chapter": {}, "pending_review": 0, "gaps": 0}
    if visuals.get("pending_review"):
        gaps.append(f"{visuals['pending_review']} 个原图资产待教师审核")
    unresolved = visuals.get('unresolved_gaps', visuals.get('gaps', 0))
    if unresolved:
        gaps.append(f"{unresolved} 个原图资产缺失/占位/哈希异常")
    status = str(manifest.get("status") or "unknown")
    if status not in ("ready", "published", "released"):
        gaps.append(f"教材发布清单状态为 {status}")
    ready = not gaps and bool(chapters) and bool(index_sha)
    identity = {
        "course_id": course_id,
        "manifest_sha256": _sha256(PSYCHOLOGY_DIR / "manifest.json"),
        "pdf_manifest_sha256": _sha256(PSYCHOLOGY_DIR / "pdf_manifest.json"),
        "status": status,
        "chapters": chapters,
        "index_sha256": index_sha,
        "visuals": {key: visuals.get(key) for key in ("total", "by_chapter", "pending_review")},
    }
    release_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return identity | {
        "title": manifest.get("title") or course_id,
        "ready": ready,
        "gaps": gaps,
        "release_id": release_id,
        "visuals": visuals,
    }


def clear_cache():
    snapshot.cache_clear()
    from knowledge.source_visuals import clear_cache as clear_visual_cache
    clear_visual_cache()


def validate(expected=None, *, refresh=True) -> dict:
    """Return the current release, rejecting a changed release identity."""
    if refresh:
        clear_cache()
    current = snapshot()
    if expected is not None:
        expected_id = expected.get("release_id") if isinstance(expected, dict) else str(expected)
        if expected_id and current["release_id"] != expected_id:
            raise ValueError("教材发布版本已变化，请重新建立来源绑定")
    return current


def binding() -> dict:
    state = validate()
    return {"release_id": state["release_id"], "status": state["status"],
            "ready": state["ready"], "gaps": state["gaps"]}
