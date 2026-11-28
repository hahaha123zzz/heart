"""恢复学生当前会话分支中已发布的教材引用。"""
from __future__ import annotations

import re
from urllib.parse import unquote

_PREVIOUS = re.compile(r"上[一个]?(?:轮|条|次|一条|一轮)|刚才|前面|前一条|上文")
_EVIDENCE = re.compile(r"原文|证据|引用|出处|第[一二三四五六七八九十\d]+条|哪一页")
_LINK = re.compile(
    r'\[教材[^\]\n]+\]\(#dt-material-([0-9a-f]{16})-revision-(\d+)-locator-(\d+)'
    r'\?quote=([%\w.~-]+)(?: "citation")?\)'
)
_SHORT_QUESTION = re.compile(
    r"(?:请问[，,\s]*)?(?:(?:今天|明天|昨天|现在)(?:是)?(?:几月几日|几号|星期几|周几|什么日期|几月几号|几点)"
    r"|你好|您好|你是谁|你是什么模型)[？?。！!\s]*(?:只回答日期[。！!\s]*)?"
)


def standalone_question(text: str, payload: dict) -> bool:
    viewport = payload.get("reading_viewport") or {}
    return bool(
        _SHORT_QUESTION.fullmatch(text.strip())
        and not viewport.get("selection")
        and not viewport.get("legacy_reader_selection")
        and not payload.get("attachments")
    )


def asks_for_previous_evidence(text: str) -> bool:
    return bool(_PREVIOUS.search(text) and _EVIDENCE.search(text))


def restore_cited_evidence(messages) -> dict:
    """按上一条助手答复中的引用顺序恢复原文，逐条重新确认授权及定位。"""
    from deeptutor.multi_user.learning_access import learning_material_allowed
    from deeptutor.reading import ReadingStore
    from knowledge.citation_index import locate_pdf_page_quote
    from knowledge.fixed_book import digest
    from knowledge.pdf_reader import documents, pdf_path

    answer = next((row.get("content") or "" for row in reversed(messages)
                   if row.get("role") == "assistant"), "")
    links = {}
    for match in _LINK.finditer(answer):
        links.setdefault(match.groups(), match.group())
    if not links:
        return {}
    materials = {row["version"][:16]: row for row in documents()}
    store = ReadingStore()
    recovered = {}
    for ordinal, ((material, revision, locator, encoded), citation) in enumerate(links.items(), 1):
        row = materials.get(material)
        page = int(locator)
        quote = unquote(encoded)
        if (not row or not learning_material_allowed(material)
                or not 1 <= page <= row["page_count"] or not quote.strip()):
            continue
        try:
            manifest = store.manifest(material)
            path = pdf_path(row)
            if (manifest.document_id != row["document_id"] or manifest.version != row["version"]
                    or manifest.revision != int(revision) or digest(path) != row["version"]
                    or not locate_pdf_page_quote(path, page, quote)):
                continue
        except (OSError, ValueError, KeyError):
            continue
        recovered[f"S{ordinal}"] = {
            "reader_citation": citation, "text": quote, "page": page,
            "chapter_id": row["chapter_id"], "document_id": row["document_id"],
            "version": row["version"], "short_id": f"S{ordinal}",
        }
    return recovered
