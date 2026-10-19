# Adapted from HKUDS/DeepTutor 6cf793bd868ba5ecbe64722936d4be8fab5a01df; see third_party/DeepTutor.
"""Optional cross-encoder reranking for the LlamaIndex pipeline."""

from __future__ import annotations

from collections import OrderedDict
import logging
import math
from threading import Lock
from typing import Any, Callable

from llama_index.core.schema import MetadataMode, NodeWithScore

logger = logging.getLogger(__name__)

_RERANKER_CACHE: "OrderedDict[tuple[str, str], Any]" = OrderedDict()
_RERANKER_CACHE_LOCK = Lock()
_RERANKER_CACHE_MAXSIZE = 2


def clear_reranker_cache() -> None:
    """Drop cached reranker models (used by tests and settings changes)."""
    with _RERANKER_CACHE_LOCK:
        _RERANKER_CACHE.clear()


def _load_cross_encoder(model_name: str) -> Any:
    """复用项目已验证设备的FastEmbed/FlagEmbedding，不另下载SentenceTransformers模型。"""
    from knowledge.hybrid_retrieval import _reranker
    backend, model = _reranker(model_name)
    class ProjectCrossEncoder:
        def predict(self, pairs, **kwargs):
            if backend == 'flag': return model.compute_score(pairs)
            query = pairs[0][0]
            return list(model.rerank(query, [pair[1] for pair in pairs], batch_size=4))
    return ProjectCrossEncoder()


def _cross_encoder(
    model_name: str,
    loader: Callable[[str], Any] | None = None,
) -> Any | None:
    from knowledge.inference_runtime import configured_device
    cache_key = (model_name, configured_device('RERANK'))
    with _RERANKER_CACHE_LOCK:
        cached = _RERANKER_CACHE.get(cache_key)
        if cached is not None:
            _RERANKER_CACHE.move_to_end(cache_key)
            return cached

    try:
        model = (loader or _load_cross_encoder)(model_name)
    except ImportError:
        logger.warning(
            "Reranker model %r is configured, but the project's reranker dependency is unavailable; "
            "using embedding retrieval unchanged.",
            model_name,
        )
        return None
    except Exception as exc:
        logger.warning(
            "Failed to load reranker model %r; using embedding retrieval unchanged: %s",
            model_name,
            exc,
        )
        return None

    with _RERANKER_CACHE_LOCK:
        _RERANKER_CACHE[cache_key] = model
        _RERANKER_CACHE.move_to_end(cache_key)
        while len(_RERANKER_CACHE) > _RERANKER_CACHE_MAXSIZE:
            _RERANKER_CACHE.popitem(last=False)
    return model


def _sigmoid(value: float) -> float:
    """Convert cross-encoder logits to a stable 0..1 source score."""
    try:
        if value >= 0:
            return 1.0 / (1.0 + math.exp(-value))
        exp_value = math.exp(value)
        return exp_value / (1.0 + exp_value)
    except (OverflowError, ValueError):
        return 1.0 if value > 0 else 0.0


def _identity_logits(scores: Any) -> Any:
    """Request raw cross-encoder logits from SentenceTransformers."""
    return scores


def rerank_nodes(
    query: str,
    nodes: list[Any],
    *,
    top_k: int,
    model_name: str,
    loader: Callable[[str], Any] | None = None,
    trace: dict | None = None,
) -> list[Any]:
    """Rerank LlamaIndex results and return at most ``top_k`` nodes.

    Missing optional dependencies and model-load failures are non-fatal: the
    first-stage ordering is returned so saved knowledge remains searchable.
    """
    requested = max(1, int(top_k))
    if trace is not None: trace['rerank_status'] = 'disabled'
    if not query or not nodes or not model_name:
        return nodes[:requested]

    model = _cross_encoder(model_name, loader)
    if model is None:
        if trace is not None: trace['rerank_status'] = 'unavailable'
        return nodes[:requested]

    pairs = [(query, result.node.get_content(metadata_mode=MetadataMode.LLM)) for result in nodes]
    try:
        raw_scores = list(model.predict(pairs, activation_fct=_identity_logits))
        if len(raw_scores) != len(nodes) or not all(math.isfinite(float(score)) for score in raw_scores):
            raise ValueError('重排分数数量或数值无效')
        ranked = sorted(
            (
                (index, float(score))
                for index, score in enumerate(raw_scores)
                if math.isfinite(float(score))
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:requested]
    except Exception as exc:
        if trace is not None: trace['rerank_status'] = 'failed'
        logger.warning(
            "Reranker model %r failed while scoring %d candidates; "
            "using embedding retrieval unchanged: %s",
            model_name,
            len(nodes),
            exc,
        )
        return nodes[:requested]

    if trace is not None: trace['rerank_status'] = 'applied'
    return [NodeWithScore(node=nodes[index].node, score=_sigmoid(score)) for index, score in ranked]


__all__ = ["clear_reranker_cache", "rerank_nodes"]
