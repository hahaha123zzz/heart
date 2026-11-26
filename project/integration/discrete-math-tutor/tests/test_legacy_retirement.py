"""旧教材索引默认停用；离线测试或归档工具必须显式启用。"""
import pytest

from knowledge import legacy_retirement, textbook
from knowledge.local_rag import course_retrieval


def test_legacy_index_is_retired_by_default(monkeypatch):
    monkeypatch.delenv('HEART_LEGACY_INDEX_ENABLED', raising=False)
    assert legacy_retirement.enabled() is False
    with pytest.raises(RuntimeError, match='旧教材索引已退役'):
        legacy_retirement.require()
    with pytest.raises(RuntimeError, match='旧教材索引已退役'):
        course_retrieval.retrieve('自变量是什么')
    textbook.load_textbook.cache_clear()
    with pytest.raises(RuntimeError, match='旧教材索引已退役'):
        textbook.load_textbook()


def test_legacy_index_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv('HEART_LEGACY_INDEX_ENABLED', '1')
    legacy_retirement.require()
