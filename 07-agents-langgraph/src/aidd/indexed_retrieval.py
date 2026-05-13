"""Извлечение документов по строке запроса: режим из `RAG_RETRIEVAL_MODE` (semantic / hybrid / hybrid_rerank)."""

from __future__ import annotations

import aidd.hf_hub_env  # noqa: F401 — до импортов с HF Hub

import asyncio
import logging
from typing import Any, Sequence

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables.config import RunnableConfig
from langchain_core.vectorstores import InMemoryVectorStore

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from openai import APIStatusError
from sentence_transformers import CrossEncoder

from aidd.config import AppConfig
from aidd.llm_client import (
    LlmInsufficientCreditsError,
    LlmInvocationError,
    is_insufficient_credits_error,
)
from aidd.vector_index import VectorIndexState

logger = logging.getLogger(__name__)


def documents_from_retriever_output(retrieved: object) -> tuple[Document, ...]:
    docs_raw = retrieved if isinstance(retrieved, list) else list(retrieved)
    return tuple(doc for doc in docs_raw if isinstance(doc, Document))


def cap_hybrid_documents(docs_tuple: tuple[Document, ...], limit: int) -> tuple[Document, ...]:
    if len(docs_tuple) <= limit:
        return docs_tuple
    return docs_tuple[:limit]


class IndexedRetriever:
    """Retriever + финальный топ (cap / cross-encoder) поверх уже построенного индекса."""

    def __init__(self, config: AppConfig, vector_index: VectorIndexState) -> None:
        self._config = config
        self._vector_index = vector_index
        self._cross_encoder: CrossEncoder | None = None
        if config.rag_retrieval_mode == "hybrid_rerank":
            logger.info("CrossEncoder (rerank): %s", config.cross_encoder_model)
            self._cross_encoder = CrossEncoder(config.cross_encoder_model)

    @property
    def rag_retrieval_mode(self) -> str:
        return self._config.rag_retrieval_mode

    def build_retriever(self, store: InMemoryVectorStore) -> BaseRetriever:
        cfg = self._config
        if cfg.rag_retrieval_mode == "semantic":
            return store.as_retriever(search_kwargs={"k": cfg.semantic_k})
        if cfg.rag_retrieval_mode in ("hybrid", "hybrid_rerank"):
            chunks = self._vector_index.get_chunk_documents()
            if not chunks:
                logger.warning("RAG hybrid: chunk list is missing")
                raise LlmInvocationError()
            sem_k = cfg.semantic_k
            bm_k = cfg.bm25_k
            if cfg.rag_retrieval_mode == "hybrid_rerank":
                pool = cfg.rerank_candidate_pool
                sem_k = max(sem_k, pool)
                bm_k = max(bm_k, pool)
            bm25 = BM25Retriever.from_documents(chunks)
            bm25.k = bm_k
            semantic_r = store.as_retriever(search_kwargs={"k": sem_k})
            return EnsembleRetriever(
                retrievers=[semantic_r, bm25],
                weights=[cfg.hybrid_semantic_weight, cfg.hybrid_bm25_weight],
            )
        raise LlmInvocationError()

    def finalize_documents(
        self,
        search_query: str,
        fused_docs: tuple[Document, ...],
    ) -> tuple[Document, ...]:
        cfg = self._config
        if cfg.rag_retrieval_mode == "semantic":
            return fused_docs
        if cfg.rag_retrieval_mode == "hybrid":
            return cap_hybrid_documents(fused_docs, cfg.semantic_k + cfg.bm25_k)
        pool_docs = cap_hybrid_documents(fused_docs, cfg.rerank_candidate_pool)
        if not pool_docs or self._cross_encoder is None:
            return pool_docs
        pairs = [(search_query, d.page_content) for d in pool_docs]
        scores = self._cross_encoder.predict(pairs)
        ranked = sorted(zip(pool_docs, scores), key=lambda x: x[1], reverse=True)
        top_k = cfg.rerank_top_k
        return tuple(d for d, _ in ranked[:top_k])

    async def aretrieve(
        self,
        search_query: str,
        *,
        config: RunnableConfig | None = None,
    ) -> tuple[Document, ...]:
        store = self._vector_index.get_store()
        if store is None:
            logger.warning("RAG: vector store is missing")
            raise LlmInvocationError()
        retriever = self.build_retriever(store)
        try:
            retrieved = await retriever.ainvoke(search_query, config=config)
        except Exception as exc:
            if isinstance(exc, APIStatusError):
                if exc.status_code == 402:
                    raise LlmInsufficientCreditsError() from exc
                logger.warning("RAG retrieve API status error: %s", exc.status_code)
                raise LlmInvocationError() from exc
            if is_insufficient_credits_error(exc):
                raise LlmInsufficientCreditsError() from exc
            logger.warning("RAG retrieve failed: %s: %s", type(exc).__name__, exc)
            raise LlmInvocationError() from exc

        fused = documents_from_retriever_output(retrieved)
        if self._config.rag_retrieval_mode == "hybrid_rerank":
            docs_tuple = await asyncio.to_thread(
                self.finalize_documents, search_query, fused
            )
        else:
            docs_tuple = self.finalize_documents(search_query, fused)
        return docs_tuple


def documents_to_sources_payload(docs: Sequence[Document]) -> list[dict[str, Any]]:
    """Структура элементов для JSON инструмента `rag_search` (vision §8)."""
    from pathlib import Path

    out: list[dict[str, Any]] = []
    for doc in docs:
        meta = dict(doc.metadata or {})
        raw_src = meta.get("source")
        name = Path(str(raw_src)).name if raw_src else "unknown"
        page_meta = meta.get("page")
        page_out: int | None
        if isinstance(page_meta, int):
            page_out = page_meta + 1
        else:
            page_out = None
        out.append(
            {
                "source": name,
                "page_content": doc.page_content or "",
                "page": page_out,
            }
        )
    return out

