"""Local embeddings: no API, no quota, nothing leaves the server.

multilingual-e5-large understands French, Arabic and (roughly) Darija.
e5 models expect a "query: " / "passage: " prefix on every text.
"""
import asyncio
import threading

from .config import settings

_lock = threading.Lock()
_model_obj = None


def _model():
    global _model_obj
    with _lock:  # load once, even if two requests arrive together
        if _model_obj is None:
            from fastembed import TextEmbedding

            _model_obj = TextEmbedding(settings.local_embed_model)
    return _model_obj


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed([f"passage: {t}" for t in texts], batch_size=16)]


def embed_queries(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed([f"query: {t}" for t in texts])]


async def aembed_queries(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(embed_queries, texts)


def warm_up() -> None:
    embed_queries(["warm up"])
    if settings.use_rerank:
        rerank("warm up", ["warm up"])


_rr_obj = None


def _reranker():
    global _rr_obj
    with _lock:
        if _rr_obj is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            _rr_obj = TextCrossEncoder(settings.rerank_model)
    return _rr_obj


def rerank(query: str, docs: list[str]) -> list[float]:
    """Cross-encoder: reads question + passage together -> relevance score."""
    return [float(s) for s in _reranker().rerank(query, docs)]


async def arerank(query: str, docs: list[str]) -> list[float]:
    return await asyncio.to_thread(rerank, query, docs)
