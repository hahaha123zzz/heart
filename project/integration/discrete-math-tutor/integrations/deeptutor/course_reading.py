"""把宿主已校验的课程 PDF 导入原生阅读材料。

导入按内容哈希幂等：同一份教材重复调用不会重复抽取，也不会覆盖批注。
宿主在教学请求前调用，保证沉浸阅读能力拿到的是与教材清单一致的原文。
"""
from __future__ import annotations

from threading import Lock
from hashlib import file_digest

_LOCK = Lock()


def _course_documents():
    from knowledge.course_config import COURSE_ID, COURSE_TITLE, PSYCHOLOGY_DIR
    from knowledge.pdf_reader import documents, pdf_path

    if not PSYCHOLOGY_DIR.is_dir():
        raise ValueError(f"教材目录不存在：{PSYCHOLOGY_DIR.name}")
    rows = []
    for record in documents():
        path = pdf_path(record)
        if not path.is_file():
            raise ValueError(f"教材 PDF 不存在：{path.name}")
        with path.open('rb') as stream:
            if file_digest(stream, 'sha256').hexdigest() != record['version']:
                raise ValueError('教材 PDF 与正式版本不一致')
        rows.append({"document_id": record["document_id"], "version": record['version'], "chapter_id": record.get("chapter_id"),
                     "title": record.get("title") or path.stem, "path": path})
    if not rows:
        raise ValueError("课程没有可导入的教材 PDF")
    return COURSE_ID, COURSE_TITLE, rows


def ensure_course_reading() -> dict:
    """导入并返回 {course_id, course_title, workspace_id, active_material_id, materials}。"""
    from deeptutor.reading import ReadingCatalogStore, ReadingStore

    course_id, course_title, rows = _course_documents()
    with _LOCK:
        catalog = ReadingCatalogStore()
        store = ReadingStore()
        materials = []
        for row in rows:
            # 原生库按内容哈希幂等，并在当前用户/工作区中读写；同名文件不代表同一版本。
            manifest = store.ingest(row["path"])
            existing = catalog.find_material_by_content(manifest.material_id)
            if existing is None or existing.status != 'ready':
                existing = catalog.register_manifest(manifest)
            material_id, filename = existing.material_id, existing.filename
            materials.append({"document_id": row["document_id"], "chapter_id": row["chapter_id"],
                              "material_id": material_id, "filename": filename, "version": row['version']})
        ids = [row["material_id"] for row in materials]
        workspace = next((row for row in catalog.list_workspaces(search=course_title)
                          if row.title == course_title), None)
        if workspace is None:
            workspace = catalog.create_workspace(course_title, ids,
                description=f"{course_id} 正式教材，由宿主导入")
        else:
            present = {tab.material.material_id for tab in workspace.tabs}
            for material_id in ids:
                if material_id not in present:
                    catalog.add_material(workspace.workspace_id, material_id)
            workspace = catalog.get_workspace(workspace.workspace_id)
        active = workspace.active_material_id if workspace.active_material_id in ids else ids[0]
        catalog.set_active_material(workspace.workspace_id, active)
        result = {"course_id": course_id, "course_title": course_title,
                  "workspace_id": workspace.workspace_id, "active_material_id": active,
                  "materials": materials}
        return result


def material_for_chapter(prepared: dict, chapter_id=None, document_id=None) -> str:
    """按章节或文档选择材料；找不到时退回当前活动材料。"""
    for row in prepared.get("materials", ()):
        if document_id and row["document_id"] == document_id:
            return row["material_id"]
    for row in prepared.get("materials", ()):
        if chapter_id is not None and row["chapter_id"] == chapter_id:
            return row["material_id"]
    return prepared["active_material_id"]
