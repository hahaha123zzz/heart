from types import SimpleNamespace
from urllib.parse import quote

# Imported before any monkeypatching so citation_index binds the real
# documents/pdf_path/digest instead of this module's fake fixtures.
import knowledge.citation_index  # noqa: F401

from integrations.deeptutor.history_evidence import (
    asks_for_previous_evidence,
    restore_cited_evidence,
    standalone_question,
)


def test_date_with_open_reader_but_no_selection_is_independent():
    viewport = {"document_id": "chapter-01", "locator": 7}
    question = "今天几号？只回答日期。"
    assert standalone_question(question, {"reading_viewport": viewport})
    assert not standalone_question(question, {"reading_viewport": {**viewport, "selection": "原文"}})
    assert not standalone_question(question, {"attachments": [{"type": "image"}]})
    assert not standalone_question("今天教材里讲的概念是什么？", {})
    assert not standalone_question("继续", {})


def test_restore_uses_visible_order_revalidates_and_does_not_renumber_missing_sources(monkeypatch):
    alpha, beta = "a" * 64, "b" * 64
    text = "自变量是研究者操纵的因素。"
    def link(version, passage):
        return f'[教材第1章第7页](#dt-material-{version[:16]}-revision-1-locator-7?quote={quote(passage)} "citation")'
    first, second = link(alpha, "未授权原文"), link(beta, text)
    documents = [
        {"version": alpha, "document_id": "chapter-01", "chapter_id": 1, "page_count": 10},
        {"version": beta, "document_id": "chapter-02", "chapter_id": 2, "page_count": 10},
    ]
    monkeypatch.setattr("knowledge.pdf_reader.documents", lambda: documents)
    monkeypatch.setattr("knowledge.pdf_reader.pdf_path", lambda row: row["document_id"])
    monkeypatch.setattr("knowledge.fixed_book.digest", lambda _: beta)
    # citation_index binds fixed_book.digest at import; patch that binding too so
    # this test cannot leave a fake digest behind for later LiveCitationIndex users.
    monkeypatch.setattr("knowledge.citation_index.fixed_digest", lambda _: beta)
    monkeypatch.setattr("deeptutor.multi_user.learning_access.learning_material_allowed", lambda mid: mid == beta[:16])
    monkeypatch.setattr("deeptutor.reading.ReadingStore", lambda: SimpleNamespace(
        manifest=lambda _: SimpleNamespace(document_id="chapter-02", version=beta, revision=1)))
    monkeypatch.setattr("knowledge.citation_index.locate_pdf_page_quote",
                        lambda path, page, value: [object()] if (path, page, value) == ("chapter-02", 7, text) else [])
    assert asks_for_previous_evidence("请继续解释你上一条回答引用的第一条教材证据")
    assert not asks_for_previous_evidence("自变量是什么")
    result = restore_cited_evidence([
        {"role": "assistant", "content": link(beta, "旧回答不参与")},
        {"role": "assistant", "content": f"{first}{second}{second}{link(beta, '未命中原文')}"},
        {"role": "user", "content": "追问上一条"},
    ])
    assert list(result) == ["S2"]
    assert result["S2"]["text"] == text
    assert result["S2"]["reader_citation"] == second
