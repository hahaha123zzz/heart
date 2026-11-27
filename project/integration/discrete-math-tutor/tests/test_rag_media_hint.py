"""教材检索结果附带可展示的原图 ID，供回答按 media: 引用。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "vendor/DeepTutor"))

from integrations.deeptutor.course_rag_provider import source_content


def test_source_content_lists_verified_media_ids():
    text = source_content([{
        'index': 1, 'short_id': 'S1', 'chapter_id': 2, 'page': 32,
        'rag_source_id': 'rag-1', 'location': {'section': '第一节'},
        'text': '正文', 'image_refs': [{'id': 'image-01-0002', 'label': '图2-1'}],
    }])
    assert '![图2-1](media:image-01-0002)' in text
