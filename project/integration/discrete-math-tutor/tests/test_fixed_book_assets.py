"""教材资产安装：完整核对后发布，普通加载只核对身份和文件大小。"""
import hashlib
import json
from pathlib import Path

import pytest

from knowledge.fixed_book_assets import AssetsMismatch, install, load


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree(root, files):
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def fixture(tmp_path):
    candidate = tmp_path / "candidate"
    textbook = tmp_path / "textbook"
    frozen = candidate / "input"
    tree(frozen, {
        "chapters/chapter_01/document.json": '{"chapter_id":1}',
        "manifest.json": '{"course_id":"experimental-psychology-3"}',
        "pdf_manifest.json": "[]",
    })
    allowed = {relative: digest(frozen / relative) for relative in (
        "chapters/chapter_01/document.json", "manifest.json", "pdf_manifest.json")}
    tree(candidate, {
        "input_manifest.json": json.dumps({"files": allowed}),
        "progress.json": '{"state":"ready"}',
        "index_files.json": "[]",
        "policy.json": "{}",
        "source_map.json": '{"chapter_01.generated.pdf":{"chapter_id":1}}',
    })
    tree(textbook, {
        "chapters/chapter_01/document.json": '{"chapter_id":1}',
        "manifest.json": '{"course_id":"experimental-psychology-3"}',
        "pdf_manifest.json": "[]",
        "rag_index.sqlite3": "legacy-index",
    })
    return candidate, textbook


def test_install_then_load_uses_the_published_record(tmp_path):
    candidate, textbook = fixture(tmp_path)
    assets = tmp_path / "private/textbook-assets"
    record = install(assets, textbook, candidate, release_id="release-a",
                     source_map={"chapter_01.generated.pdf": {"chapter_id": 1}})
    assert record["release_id"] == "release-a"
    assert record["host_extras"]["count"] == 1
    loaded = load(assets, textbook, candidate)
    assert loaded["textbook"]["files"]["manifest.json"] == digest(textbook / "manifest.json")
    assert loaded["source_map"] == {"chapter_01.generated.pdf": {"chapter_id": 1}}


def test_load_fails_when_a_required_textbook_file_changed_or_missing(tmp_path):
    candidate, textbook = fixture(tmp_path)
    assets = tmp_path / "assets"
    install(assets, textbook, candidate, release_id="r", source_map={})
    (textbook / "rag_index.sqlite3").unlink()
    with pytest.raises(AssetsMismatch, match="教材资产缺失或已变化"):
        load(assets, textbook, candidate)


def test_load_fails_when_the_candidate_index_changed(tmp_path):
    candidate, textbook = fixture(tmp_path)
    assets = tmp_path / "assets"
    install(assets, textbook, candidate, release_id="r", source_map={})
    (candidate / "progress.json").write_text('{"state":"rebuilt"}', encoding="utf-8")
    with pytest.raises(AssetsMismatch, match="与当前 LightRAG 索引不一致"):
        load(assets, textbook, candidate)


def test_load_without_a_record_falls_back_to_scanning(tmp_path):
    candidate, textbook = fixture(tmp_path)
    assert load(tmp_path / "assets", textbook, candidate) is None


def test_failed_install_keeps_the_previous_record(tmp_path):
    candidate, textbook = fixture(tmp_path)
    assets = tmp_path / "assets"
    first = install(assets, textbook, candidate, release_id="old", source_map={})
    (candidate / "input/manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(Exception):
        install(assets, textbook, candidate, release_id="new", source_map={})
    assert json.loads((assets / "assets.json").read_text(encoding="utf-8")) == first


def test_validate_uses_the_install_record_without_scanning(tmp_path, monkeypatch):
    from knowledge.lightrag import retrieval, storage
    from knowledge.lightrag.course_input import COURSE

    candidate = tmp_path / "candidate"
    (candidate / "index").mkdir(parents=True)
    files = {f"chapters/chapter_{index:02d}/document.json": f"sha{index}" for index in range(1, 12)}
    (candidate / "input_manifest.json").write_text(
        json.dumps({"course_id": COURSE, "files": files}), encoding="utf-8")
    (candidate / "progress.json").write_text(json.dumps({
        "state": "candidate_complete",
        "chapters": {str(index): {"complete": True} for index in range(1, 12)},
    }), encoding="utf-8")
    (candidate / "index_files.json").write_text("[]", encoding="utf-8")
    (candidate / "policy.json").write_text("{}", encoding="utf-8")
    (candidate / "source_map.json").write_text("{}", encoding="utf-8")
    (tmp_path / "textbook").mkdir()
    assets = {"frozen": {"files": files}, "host_extras": {"count": 3, "sha256": "abc"}}
    backend = retrieval.LightRagBackend(candidate, authorized_course_ids={COURSE},
                                        allow_candidate=True, source_root=tmp_path / "textbook")
    monkeypatch.setattr(storage, "verify_manifest", lambda *arguments, **keywords: {})
    monkeypatch.setattr(retrieval, "verify",
                        lambda *arguments, **keywords: (_ for _ in ()).throw(AssertionError("scanned frozen input")))
    monkeypatch.setattr(retrieval, "verify_active",
                        lambda *arguments, **keywords: (_ for _ in ()).throw(AssertionError("scanned textbook")))
    snapshot = {}
    manifest = backend.validate(COURSE, snapshot=snapshot, assets=assets)
    assert manifest["course_id"] == COURSE
    assert snapshot["additional_host_files"] == {"count": 3, "sha256": "abc", "evidence_eligible": False}
