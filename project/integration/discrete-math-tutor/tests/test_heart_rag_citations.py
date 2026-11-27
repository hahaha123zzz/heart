import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs

from integrations.deeptutor import heart_rag


def _catalog_documents():
    return [
        {"chapter_id": 1, "title": "第一章 实验心理学概述", "version": "a" * 64,
         "document_id": "doc-1", "page_count": 12,
         "sections": [{"id": 1, "title": "第一节"}, {"id": 2, "title": "第二节"}],
         "pages": [{"page": 1, "text": "页面正文哨兵一"},
                   {"page": 2, "text": "页面正文哨兵二"}]},
        {"chapter_id": 2, "title": "第二章 变量与控制", "version": "b" * 64,
         "document_id": "doc-2",
         "sections": [{"id": 1, "title": "第一节"}],
         "pages": [{"page": 1, "text": "页面正文哨兵三"},
                   {"page": 2, "text": "页面正文哨兵四"},
                   {"page": 3, "text": "页面正文哨兵五"}]},
    ]


def _run_catalog(monkeypatch, **kwargs):
    from knowledge import pdf_reader

    monkeypatch.setattr(pdf_reader, "documents", _catalog_documents)
    return asyncio.run(heart_rag.HeartCourseFilesTool().execute(**kwargs))


def test_catalog_projects_only_chapter_metadata(monkeypatch):
    result = _run_catalog(monkeypatch)
    content = result.content

    assert "第1章" in content and "第一章 实验心理学概述" in content
    assert "12 页" in content and "2 节" in content
    assert "doc-1" in content
    for sentinel in ("页面正文哨兵一", "页面正文哨兵二", "页面正文哨兵三"):
        assert sentinel not in content
    assert not result.sources
    assert "目录" in heart_rag.HeartCourseFilesTool().get_definition().description


def test_catalog_filters_by_chapter_title(monkeypatch):
    content = _run_catalog(monkeypatch, pattern="变量").content

    assert "第2章" in content
    assert "第1章" not in content
    assert "教材共 2 章，当前列出 1 章" in content


def test_catalog_reports_no_matching_chapter(monkeypatch):
    content = _run_catalog(monkeypatch, pattern="不存在的章节").content

    assert "没有匹配" in content
    assert "第1章" not in content and "第2章" not in content


def test_catalog_lists_only_authorized_versions(monkeypatch):
    from deeptutor.multi_user import context as user_context, learning_access

    user = SimpleNamespace(username="learner", id="learner-id", is_admin=False)
    token = user_context.set_current_user(user)
    try:
        monkeypatch.setattr(learning_access, "learning_material_allowed",
                            lambda material_id: material_id == "a" * 16)
        content = _run_catalog(monkeypatch).content
    finally:
        user_context.reset_current_user(token)

    assert "第1章" in content
    assert "第2章" not in content
    assert "当前列出 1 章" in content


def test_catalog_derives_page_count_when_legacy_manifest_lacks_it(monkeypatch):
    content = _run_catalog(monkeypatch).content

    chapter_two = next(line for line in content.splitlines() if "第2章" in line)
    assert "3 页" in chapter_two
    assert "页面正文哨兵三" not in content


def test_catalog_reports_omitted_chapters(monkeypatch):
    result = _run_catalog(monkeypatch, limit=1)

    assert "当前列出 1 章" in result.content
    assert "另有 1 章未列出" in result.content
    assert "第2章" not in result.content


def test_reader_citation_contains_verified_chapter_page_version_and_quote(monkeypatch):
    import deeptutor.reading

    version = "a" * 64
    manifest = SimpleNamespace(
        document_id="experimental-psychology-3:chapter-03",
        version=version,
        revision=4,
    )

    class FakeStore:
        def manifest(self, material_id):
            assert material_id == version[:16]
            return manifest

    monkeypatch.setattr(deeptutor.reading, "ReadingStore", FakeStore)
    citation = heart_rag._reader_citation({
        "document_id": manifest.document_id,
        "version": version,
        "chapter_id": 3,
        "page": 12,
        "quote": "研究者操纵自变量，并观察因变量的变化。",
    })
    assert citation.startswith("[教材第3章第12页](#dt-material-" + version[:16])
    assert "-revision-4-locator-12?quote=" in citation
    href = citation.split("](", 1)[1].split(' "citation")', 1)[0]
    assert parse_qs(href.split("?", 1)[1])["quote"][0] == "研究者操纵自变量，并观察因变量的变化。"
    assert '"citation")' in citation


def test_reader_citation_shortens_long_quote_at_a_sentence_boundary(monkeypatch):
    import deeptutor.reading

    version = "e" * 64
    monkeypatch.setattr(deeptutor.reading, "ReadingStore", lambda: SimpleNamespace(
        manifest=lambda _: SimpleNamespace(
            document_id="experimental-psychology-3:chapter-09", version=version, revision=1)))
    long_quote = "注意研究中的自变量比较多。" + "这是一段很长的补充说明" * 30 + "。"
    citation = heart_rag._reader_citation({
        "document_id": "experimental-psychology-3:chapter-09",
        "version": version,
        "chapter_id": 9,
        "page": 1,
        "quote": long_quote,
    })
    href = citation.split("](", 1)[1].split(' "citation")', 1)[0]
    quote = parse_qs(href.split("?", 1)[1])["quote"][0]
    assert len(quote) <= 240
    assert quote.endswith("。")
    assert long_quote.startswith(quote)


def test_course_evidence_keeps_only_linked_sources_and_respects_limit(monkeypatch):
    from integrations.deeptutor import heart_rag

    monkeypatch.setattr(heart_rag, "_retrieve_rows", lambda query: [object(), object(), object()])
    monkeypatch.setattr(heart_rag, "_authorized_course_rows", lambda rows: rows)
    monkeypatch.setattr('integrations.deeptutor.native_grounding.prepare_retrieval', lambda *_: [
        {"chapter_id": 1, "page": None, "section_id": 1, "document_id": "d", "version": "a" * 64,
         "text": "原文一", "quote": "原文一", "location": {"evidence": {"rects": [{"page": 7}]}}},
        {"chapter_id": 1, "page": None, "section_id": 1, "document_id": "d2", "version": "b" * 64,
         "text": "原文二", "quote": "原文二", "location": {"evidence": {"rects": []}}},
        {"chapter_id": 1, "page": None, "section_id": 1, "document_id": "d3", "version": "c" * 64,
         "text": "原文三", "quote": "原文三", "location": {"evidence": {"rects": [{"page": 9}]}}},
    ])
    monkeypatch.setattr(heart_rag, "_reader_citation",
                        lambda source: "[教材](#dt-material-x-revision-1-locator-7)"
                        if source["text"] != "原文二" else "")
    assert [item["text"] for item in heart_rag.course_evidence("自变量是什么", limit=3)] == ["原文一", "原文三"]
    assert len(heart_rag.course_evidence("自变量是什么", limit=1)) == 1


def test_course_evidence_degrades_to_empty_on_retrieval_error(monkeypatch):
    from integrations.deeptutor import heart_rag

    def boom(query):
        raise RuntimeError("index down")

    monkeypatch.setattr(heart_rag, "_retrieve_rows", boom)
    assert heart_rag.course_evidence("自变量是什么") == []


def test_reader_citation_uses_section_page_for_retrieved_evidence(monkeypatch):
    import deeptutor.reading
    from knowledge import pdf_reader

    version = "c" * 64
    manifest = SimpleNamespace(
        document_id="experimental-psychology-3:chapter-01",
        version=version,
        revision=2,
    )
    monkeypatch.setattr(deeptutor.reading, "ReadingStore",
                        lambda: SimpleNamespace(manifest=lambda _: manifest))
    monkeypatch.setattr(pdf_reader, "document_for_chapter",
                        lambda chapter: {"sections": [{"id": 1, "page": 1}, {"id": "2", "page": 9}]})
    citation = heart_rag._reader_citation({
        "document_id": manifest.document_id,
        "version": version,
        "chapter_id": "1",
        "section_id": "2",
        "page": None,
        "quote": "科学方法是一套通过实证证据来探寻真相的方法。",
    })
    assert citation.startswith("[教材第1章第9页](#dt-material-" + version[:16] + "-revision-2-locator-9")


def test_reader_citation_prefers_the_located_quote_page_over_the_section_page(monkeypatch):
    import deeptutor.reading
    from knowledge import pdf_reader

    version = "d" * 64
    monkeypatch.setattr(deeptutor.reading, "ReadingStore", lambda: SimpleNamespace(
        manifest=lambda _: SimpleNamespace(
            document_id="experimental-psychology-3:chapter-01", version=version, revision=1)))
    monkeypatch.setattr(pdf_reader, "document_for_chapter",
                        lambda chapter: {"sections": [{"id": 1, "page": 1}]})
    citation = heart_rag._reader_citation({
        "document_id": "experimental-psychology-3:chapter-01",
        "version": version,
        "chapter_id": "1",
        "section_id": 1,
        "page": None,
        "location": {"evidence": {"rects": [{"page": 7, "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.2}]}},
        "quote": "科学方法的特点是客观性、可重复性和可控性。",
    })
    assert "-locator-7" in citation, citation


def test_reader_citation_rejects_a_different_or_missing_reading_version(monkeypatch):
    import deeptutor.reading

    monkeypatch.setattr(
        deeptutor.reading,
        "ReadingStore",
        lambda: SimpleNamespace(manifest=lambda _: SimpleNamespace(
            document_id="some-other-document", version="b" * 64, revision=1
        )),
    )
    assert heart_rag._reader_citation({
        "document_id": "experimental-psychology-3:chapter-03",
        "version": "a" * 64,
        "chapter_id": 3,
        "page": 12,
        "quote": "依据",
    }) == ""


def test_authorized_course_rows_drop_unassigned_chapters(monkeypatch):
    from deeptutor.multi_user import context as user_context, learning_access
    from knowledge import pdf_reader

    user = SimpleNamespace(username="learner", id="learner-id", is_admin=False)
    token = user_context.set_current_user(user)
    try:
        monkeypatch.setattr(
            pdf_reader,
            "document_for_chapter",
            lambda chapter: {"version": ("a" if chapter == 1 else "b") * 64},
        )
        monkeypatch.setattr(
            learning_access,
            "learning_material_allowed",
            lambda material_id: material_id == "a" * 16,
        )
        rows = [SimpleNamespace(chapter_id=1), SimpleNamespace(chapter_id=2)]
        assert heart_rag._authorized_course_rows(rows) == rows[:1]
    finally:
        user_context.reset_current_user(token)
