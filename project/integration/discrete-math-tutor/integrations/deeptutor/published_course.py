"""把已发布教材接为上游原生 Markdown 知识库；版本目录只新增、不覆盖。"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile

HOST_ROOT = Path(__file__).resolve().parents[2]
COURSE = "experimental-psychology-3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pack(home, *, verify_files=True):
    root = Path(home).resolve() / "published" / COURSE
    pointer = root / "current.json"
    if not pointer.is_file(): raise ValueError("尚未发布教材知识库")
    active = json.loads(pointer.read_text(encoding="utf-8"))
    version = active.get("version", "")
    if len(version) != 64 or any(c not in "0123456789abcdef" for c in version):
        raise ValueError("教材发布版本无效")
    directory = root / version
    manifest_path = directory / "manifest.json"
    if sha(manifest_path) != active.get("manifest_sha256"):
        raise ValueError("教材发布清单已变化")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("course_id") != COURSE or manifest.get("version") != version or not manifest.get("files"):
        raise ValueError("教材发布清单无效")
    for relative, record in manifest["files"].items():
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
            raise ValueError("教材资源路径无效")
        note = directory / "vault" / relative
        if not note.resolve().is_relative_to((directory / "vault").resolve()) or (verify_files and sha(note) != record["sha256"]):
            raise ValueError("教材知识库文件已变化")
    return directory, manifest


def publish(home, source=None):
    from deeptutor.capabilities.obsidian.vault import create_note
    from deeptutor.services.file_io import atomic_write_json

    source = Path(source) if source is not None else HOST_ROOT / "knowledge" / "courses" / COURSE
    index = source / "rag_index.sqlite3"
    if Path(str(index) + "-wal").exists(): raise ValueError("教材索引正在写入，请稍后发布")
    documents = json.loads((source / "pdf_manifest.json").read_text(encoding="utf-8"))
    textbook = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if textbook["course_id"] != COURSE or sha(source / "source" / "textbook.docx") != textbook["source_sha256"]["textbook.docx"]:
        raise ValueError("正式教材源文件校验失败")
    for record in documents:
        chapter = record["chapter_id"]
        path = source / "chapters" / f"chapter_{chapter:02d}" / f"chapter_{chapter:02d}.generated.pdf"
        if sha(path) != record["version"]: raise ValueError("发布 PDF 与教材清单不一致")
    fingerprints = {"index": sha(index), "pdf_manifest": sha(source / "pdf_manifest.json"),
                    "manifest": sha(source / "manifest.json")}
    version = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    root = Path(home).resolve() / "published" / COURSE
    root.mkdir(parents=True, exist_ok=True)
    destination = root / version
    if not destination.exists():
        with tempfile.TemporaryDirectory(prefix=".publish-", dir=root) as temporary:
            stage = Path(temporary) / "pack"
            vault = stage / "vault"
            vault.mkdir(parents=True)
            files = {}
            db = sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True)
            db.row_factory = sqlite3.Row
            try:
                rows = db.execute("SELECT * FROM chunks ORDER BY id").fetchall()
            finally:
                db.close()
            if not rows: raise ValueError("正式教材索引为空")
            for row in rows:
                metadata = {key: row[key] for key in ("id", "chapter_id", "section_id", "page", "block_start", "block_end", "kind", "source", "section")}
                metadata["course_id"] = COURSE
                name = f"chapter-{row['chapter_id']:02d}/" + hashlib.sha256(row["id"].encode()).hexdigest() + ".md"
                create_note(vault, name, row["text"], frontmatter=metadata)
                files[name] = {"chunk_id": row["id"], "sha256": sha(vault / name)}
            if sha(index) != fingerprints["index"]: raise ValueError("发布期间教材索引已变化")
            manifest = {"course_id": COURSE, "title": textbook["title"], "version": version,
                "source_hashes": fingerprints, "documents": {record["document_id"]: record["version"] for record in documents},
                "files": files, "count": len(files), "type": "obsidian", "vector_indexed": False}
            atomic_write_json(stage / "manifest.json", manifest)
            stage.rename(destination)
    pointer = {"version": version, "manifest_sha256": sha(destination / "manifest.json")}
    # 先完整核对候选版本，再替换唯一活动指针。
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    for relative, record in manifest["files"].items():
        if sha(destination / "vault" / relative) != record["sha256"]: raise ValueError("既有知识库版本已损坏")
    atomic_write_json(root / "current.json", pointer)
    return {"course_id": COURSE, "version": version, "count": manifest["count"], "vector_indexed": False}


def register_course_knowledge(home, course_service, course_id):
    from deeptutor.knowledge.manager import KnowledgeBaseManager
    from deeptutor.services.path_service import get_path_service

    directory, manifest = read_pack(home, verify_files=False)
    name = "heart_" + manifest["version"][:24]
    manager = KnowledgeBaseManager(get_path_service().get_knowledge_bases_root())
    existing = manager.config.get("knowledge_bases", {}).get(name)
    if existing is None:
        manager.register_obsidian_vault(name, str(directory / "vault"), description="正式教材文本检索；图文证据以宿主原 PDF 校验为准")
    elif existing.get("type") != "obsidian" or Path(existing.get("vault_path", "")).resolve() != (directory / "vault").resolve():
        raise ValueError("知识库名称与既有资源冲突")
    course_service.attach_resource(course_id, kind="knowledge_base", ref_id=name, label=manifest["title"])
    return name
