"""文件后端与 PostgreSQL 后端的检索集合对照。"""
from scripts.check_lightrag_pg_parity import compare_sets


def test_compare_sets_ignores_order():
    result = compare_sets(["b", "a"], ["a", "b"])
    assert result["equal"] is True
    assert result["file_ids"] == ["a", "b"]


def test_compare_sets_detects_missing():
    result = compare_sets(["a", "b"], ["a"])
    assert result["equal"] is False
    assert result["pg_ids"] == ["a"]
