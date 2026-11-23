from types import SimpleNamespace
from urllib.parse import parse_qs

from integrations.deeptutor import heart_rag


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
