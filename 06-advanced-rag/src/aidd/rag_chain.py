"""Сборка RAG-цепочки по смыслу `rag_query_transform_chain` из `data/naive-rag.ipynb`."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.runnables.config import RunnableConfig

from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_openai import ChatOpenAI
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import InMemoryVectorStore
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


@dataclass(frozen=True)
class RagInvokeResult:
    """Ответ RAG, retrieved-документы и токены за ход (сумма по вызовам LLM в цепочке)."""

    text: str
    documents: tuple[Document, ...]
    prompt_tokens: int
    completion_tokens: int
    total_tokens_turn: int


def _aggregate_llm_usage(cb: UsageMetadataCallbackHandler) -> tuple[int, int, int]:
    """Суммирует usage по всем вызовам чата в цепочке (несколько ключей — разные model_name)."""
    inp = out = tot = 0
    for meta in cb.usage_metadata.values():
        inp += int(meta.get("input_tokens") or 0)
        out += int(meta.get("output_tokens") or 0)
        tot += int(meta.get("total_tokens") or 0)
    if tot <= 0 and (inp + out) > 0:
        tot = inp + out
    return inp, out, tot


def format_sources_for_user(documents: Sequence[Document]) -> str:
    """Строка для пользователя: файлы, для PDF — страницы (1-based), для JSON — номера записей."""
    if not documents:
        return ""

    grouped: dict[str, dict[str, set[int]]] = {}
    for doc in documents:
        meta = dict(doc.metadata or {})
        raw_src = meta.get("source")
        label = Path(str(raw_src)).name if raw_src else "unknown"

        if label not in grouped:
            grouped[label] = {"pages": set(), "indices": set()}

        page = meta.get("page")
        index = meta.get("index")

        if isinstance(page, int):
            grouped[label]["pages"].add(page + 1)
        elif isinstance(index, int):
            grouped[label]["indices"].add(index + 1)

    parts: list[str] = []
    for name in sorted(grouped.keys()):
        g = grouped[name]
        if g["pages"]:
            nums = ", ".join(str(n) for n in sorted(g["pages"]))
            parts.append(f"{name} (стр. {nums})")
        elif g["indices"]:
            nums = ", ".join(str(n) for n in sorted(g["indices"]))
            parts.append(f"{name} (запись {nums})")
        else:
            parts.append(name)

    return "; ".join(parts)


_QUERY_TRANSFORM_USER = (
    "Transform last user message to a search query in Russian language according to "
    "the whole conversation history above to further retrieve the information "
    "relevant to the conversation. Try to thorougly analyze all message to generate "
    "the most relevant query. The longer result better than short. Let it be better "
    "more abstract than specific. Only respond with the query, nothing else."
)


def _format_chunks(chunks: Sequence[object]) -> str:
    return "\n\n".join(getattr(c, "page_content", str(c)) for c in chunks)


def _answer_prompt_template(system_prompt_text: str) -> ChatPromptTemplate:
    system_with_context = (
        system_prompt_text
        + "\n\nФрагменты из справочных документов (поиск по последнему сообщению "
        "в контексте диалога):\n\n{context}"
    )
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_with_context),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def _cap_hybrid_documents(docs_tuple: tuple[Document, ...], limit: int) -> tuple[Document, ...]:
    if len(docs_tuple) <= limit:
        return docs_tuple
    return docs_tuple[:limit]


def _documents_from_retriever_output(retrieved: object) -> tuple[Document, ...]:
    docs_raw = retrieved if isinstance(retrieved, list) else list(retrieved)
    return tuple(doc for doc in docs_raw if isinstance(doc, Document))


def _map_rag_chain_exception(exc: BaseException) -> BaseException:
    if isinstance(exc, APIStatusError):
        if exc.status_code == 402:
            logger.warning("RAG LLM insufficient credits (HTTP 402)")
            return LlmInsufficientCreditsError()
        logger.warning("RAG LLM API status error: %s", exc.status_code)
        return LlmInvocationError()
    if is_insufficient_credits_error(exc):
        logger.warning("RAG LLM insufficient credits (%s)", type(exc).__name__)
        return LlmInsufficientCreditsError()
    logger.warning("RAG chain failed: %s: %s", type(exc).__name__, exc)
    return LlmInvocationError()


class RagChainRunner:
    """LCEL: query transformation по истории → retrieval → [cross-encoder rerank] → ответ LLM."""

    def __init__(self, config: AppConfig, vector_index: VectorIndexState) -> None:
        self._config = config
        self._vector_index = vector_index
        logger.info("Модель LLM (ответ бота): %s", config.llm_model)
        logger.info("Модель LLM (преобразование запроса): %s", config.llm_query_transform_model)
        logger.info("Режим retrieval: %s", config.rag_retrieval_mode)
        self._llm_query = ChatOpenAI(
            model=config.llm_query_transform_model,
            api_key=config.open_api_key,
            base_url=config.open_base_url,
            temperature=0.4,
            max_tokens=2048,
        )
        self._llm_answer = ChatOpenAI(
            model=config.llm_model,
            api_key=config.open_api_key,
            base_url=config.open_base_url,
            temperature=0.7,
            max_tokens=config.llm_max_completion_tokens,
        )
        self._query_chain = (
            ChatPromptTemplate.from_messages(
                [
                    MessagesPlaceholder(variable_name="messages"),
                    ("user", _QUERY_TRANSFORM_USER),
                ]
            )
            | self._llm_query
            | StrOutputParser()
        )
        self._answer_prompt = _answer_prompt_template(config.system_prompt_text)
        self._cross_encoder: CrossEncoder | None = None
        if config.rag_retrieval_mode == "hybrid_rerank":
            logger.info("CrossEncoder (rerank): %s", config.cross_encoder_model)
            self._cross_encoder = CrossEncoder(config.cross_encoder_model)

        self._retrieve_prepare = RunnableLambda(self._arunnable_retrieve_prepare_documents)
        self._rag_chain_lcel = (
            RunnablePassthrough.assign(search_query=self._query_chain)
            | self._retrieve_prepare
            | RunnablePassthrough.assign(context=lambda x: _format_chunks(x["documents"]))
            | RunnablePassthrough.assign(
                rag_text=self._answer_prompt | self._llm_answer | StrOutputParser()
            )
        )

    @property
    def app_config(self) -> AppConfig:
        return self._config

    def _retriever(self, store: InMemoryVectorStore) -> BaseRetriever:
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

    def _finalize_documents(
        self, search_query: str, fused_docs: tuple[Document, ...]
    ) -> tuple[Document, ...]:
        cfg = self._config
        if cfg.rag_retrieval_mode == "semantic":
            return fused_docs
        if cfg.rag_retrieval_mode == "hybrid":
            return _cap_hybrid_documents(fused_docs, cfg.semantic_k + cfg.bm25_k)
        pool_docs = _cap_hybrid_documents(fused_docs, cfg.rerank_candidate_pool)
        if not pool_docs or self._cross_encoder is None:
            return pool_docs
        pairs = [(search_query, d.page_content) for d in pool_docs]
        scores = self._cross_encoder.predict(pairs)
        ranked = sorted(zip(pool_docs, scores), key=lambda x: x[1], reverse=True)
        top_k = cfg.rerank_top_k
        return tuple(d for d, _ in ranked[:top_k])

    async def _arunnable_retrieve_prepare_documents(
        self, inp: dict[str, Any], *, config: RunnableConfig | None = None
    ) -> dict[str, Any]:
        messages = inp["messages"]
        search_query = inp["search_query"]
        store = self._vector_index.get_store()
        if store is None:
            logger.warning("RAG: vector store is missing")
            raise LlmInvocationError()
        retriever = self._retriever(store)
        cfg_run = config
        try:
            retrieved = await retriever.ainvoke(search_query, config=cfg_run)
        except Exception as e:
            raise _map_rag_chain_exception(e) from None

        fused = _documents_from_retriever_output(retrieved)
        if self._config.rag_retrieval_mode == "hybrid_rerank":
            docs_tuple = await asyncio.to_thread(
                self._finalize_documents, search_query, fused
            )
        else:
            docs_tuple = self._finalize_documents(search_query, fused)

        return {
            "messages": messages,
            "search_query": search_query,
            "documents": docs_tuple,
        }

    async def ainvoke(self, messages: list[BaseMessage]) -> RagInvokeResult:
        usage_cb = UsageMetadataCallbackHandler()
        cb_cfg = {"callbacks": [usage_cb]}

        try:
            out = await self._rag_chain_lcel.ainvoke({"messages": messages}, config=cb_cfg)
        except Exception as e:
            raise _map_rag_chain_exception(e) from None

        text = (out.get("rag_text") or "").strip()
        docs = out.get("documents") or ()
        if not isinstance(docs, tuple):
            docs = tuple(docs)
        if not text:
            logger.warning("RAG returned empty assistant message")
            raise LlmInvocationError()
        pin, pout, ptot = _aggregate_llm_usage(usage_cb)
        return RagInvokeResult(
            text=text,
            documents=docs,
            prompt_tokens=pin,
            completion_tokens=pout,
            total_tokens_turn=ptot,
        )
