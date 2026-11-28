import json

import pytest

from knowledge.lightrag.retrieval import rank_sources


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode()


def _sources():
    return [{"text": "自变量是研究者操纵的变量"}, {"text": "信度是测量结果的稳定性"}]


def test_rank_sources_uses_remote_scores(monkeypatch):
    monkeypatch.setenv("HEART_RERANK_API_URL", "https://example.test/v1/rerank")
    monkeypatch.setenv("HEART_RERANK_API_KEY", "test-key")
    seen = {}

    def urlopen(request, timeout=None):
        seen["body"] = json.loads(request.data.decode())
        seen["auth"] = request.get_header("Authorization")
        return _Response({"results": [
            {"index": 0, "relevance_score": 0.9},
            {"index": 1, "relevance_score": 0.1},
        ]})

    monkeypatch.setattr("knowledge.local_rag.rerank.urllib.request.urlopen", urlopen)
    monkeypatch.setattr(
        "knowledge.hybrid_retrieval._reranker_on_device",
        lambda *args: (_ for _ in ()).throw(AssertionError("local reranker must not load")),
    )

    selected = rank_sources("自变量", _sources())

    assert [row["text"] for row in selected] == ["自变量是研究者操纵的变量"]
    assert selected[0]["score"] == pytest.approx(0.9)
    assert seen["body"]["query"] == "自变量"
    assert seen["body"]["documents"] == [row["text"] for row in _sources()]
    assert seen["auth"] == "Bearer test-key"


def test_rank_sources_falls_back_when_api_fails(monkeypatch):
    monkeypatch.setenv("HEART_RERANK_API_URL", "https://example.test/v1/rerank")
    monkeypatch.setenv("HEART_RERANK_API_KEY", "test-key")

    def urlopen(request, timeout=None):
        raise OSError("network down")

    class Model:
        def rerank(self, query, texts, batch_size=4):
            return [5.0, -5.0]

    monkeypatch.setattr("knowledge.local_rag.rerank.urllib.request.urlopen", urlopen)
    monkeypatch.setattr(
        "knowledge.hybrid_retrieval._reranker_on_device", lambda *args: ("fastembed", Model()))

    selected = rank_sources("自变量", _sources())

    assert [row["text"] for row in selected] == ["自变量是研究者操纵的变量"]
    assert selected[0]["score"] > 0.9


def test_rank_sources_falls_back_when_api_result_is_incomplete(monkeypatch):
    monkeypatch.setenv("HEART_RERANK_API_URL", "https://example.test/v1/rerank")
    monkeypatch.setenv("HEART_RERANK_API_KEY", "test-key")

    def urlopen(request, timeout=None):
        return _Response({"results": [{"index": 0, "relevance_score": 0.9}]})

    class Model:
        def rerank(self, query, texts, batch_size=4):
            return [5.0, -5.0]

    monkeypatch.setattr("knowledge.local_rag.rerank.urllib.request.urlopen", urlopen)
    monkeypatch.setattr(
        "knowledge.hybrid_retrieval._reranker_on_device", lambda *args: ("fastembed", Model()))

    selected = rank_sources("自变量", _sources())

    assert [row["text"] for row in selected] == ["自变量是研究者操纵的变量"]
