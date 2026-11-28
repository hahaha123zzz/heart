import json

import pytest

from knowledge.lightrag.retrieval import rank_sources


def _sources():
    return [{"text": "自变量是研究者操纵的变量"}, {"text": "信度是测量结果的稳定性"}]


def test_rank_sources_uses_remote_scores(monkeypatch):
    monkeypatch.setenv("HEART_RERANK_API_URL", "https://example.test/v1/rerank")
    monkeypatch.setenv("HEART_RERANK_API_KEY", "test-key")
    seen = {}

    def post(url, key, body, timeout):
        seen.update(url=url, key=key, body=body, timeout=timeout)
        return {"results": [
            {"index": 0, "relevance_score": 0.9},
            {"index": 1, "relevance_score": 0.1},
        ]}

    monkeypatch.setattr("knowledge.local_rag.rerank._post_rerank", post)
    monkeypatch.setattr(
        "knowledge.hybrid_retrieval._reranker_on_device",
        lambda *args: (_ for _ in ()).throw(AssertionError("local reranker must not load")),
    )

    selected = rank_sources("自变量", _sources())

    assert [row["text"] for row in selected] == ["自变量是研究者操纵的变量"]
    assert selected[0]["score"] == pytest.approx(0.9)
    assert seen["url"] == "https://example.test/v1/rerank"
    assert seen["key"] == "test-key"
    assert seen["body"]["query"] == "自变量"
    assert seen["body"]["documents"] == [row["text"] for row in _sources()]


def test_rank_sources_falls_back_when_api_fails(monkeypatch):
    monkeypatch.setenv("HEART_RERANK_API_URL", "https://example.test/v1/rerank")
    monkeypatch.setenv("HEART_RERANK_API_KEY", "test-key")

    def post(url, key, body, timeout):
        raise OSError("network down")

    class Model:
        def rerank(self, query, texts, batch_size=4):
            return [5.0, -5.0]

    monkeypatch.setattr("knowledge.local_rag.rerank._post_rerank", post)
    monkeypatch.setattr(
        "knowledge.hybrid_retrieval._reranker_on_device", lambda *args: ("fastembed", Model()))

    selected = rank_sources("自变量", _sources())

    assert [row["text"] for row in selected] == ["自变量是研究者操纵的变量"]
    assert selected[0]["score"] > 0.9


def test_rank_sources_falls_back_when_api_result_is_incomplete(monkeypatch):
    monkeypatch.setenv("HEART_RERANK_API_URL", "https://example.test/v1/rerank")
    monkeypatch.setenv("HEART_RERANK_API_KEY", "test-key")

    def post(url, key, body, timeout):
        return {"results": [{"index": 0, "relevance_score": 0.9}]}

    class Model:
        def rerank(self, query, texts, batch_size=4):
            return [5.0, -5.0]

    monkeypatch.setattr("knowledge.local_rag.rerank._post_rerank", post)
    monkeypatch.setattr(
        "knowledge.hybrid_retrieval._reranker_on_device", lambda *args: ("fastembed", Model()))

    selected = rank_sources("自变量", _sources())

    assert [row["text"] for row in selected] == ["自变量是研究者操纵的变量"]


def test_rerank_http_client_is_reused(monkeypatch):
    import httpx

    import knowledge.local_rag.rerank as rerank

    rerank.clear_rerank_api_client()
    created = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            created.append(self)

        def close(self):
            pass

    monkeypatch.setattr(httpx, "Client", FakeClient)
    try:
        assert rerank._rerank_http_client() is rerank._rerank_http_client()
        assert len(created) == 1
    finally:
        rerank.clear_rerank_api_client()


def test_rerank_api_warmup_does_not_raise_on_failure(monkeypatch):
    from knowledge.local_rag import rerank

    monkeypatch.setenv("HEART_RERANK_API_URL", "https://example.test/v1/rerank")
    monkeypatch.setenv("HEART_RERANK_API_KEY", "test-key")
    monkeypatch.setattr(
        "knowledge.local_rag.rerank._post_rerank",
        lambda *args: (_ for _ in ()).throw(OSError("down")),
    )

    rerank.warm_rerank_api()
