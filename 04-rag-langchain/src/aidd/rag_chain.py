"""Сборка RAG-цепочки по смыслу `rag_query_transform_chain` из `data/naive-rag.ipynb`."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI
from openai import APIStatusError

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
    """Ответ RAG и токены за ход (сумма по вызовам LLM в цепочке)."""

    text: str
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


class RagChainRunner:
    """Query transformation → retriever top-K → ответ LLM с историей."""

    def __init__(self, config: AppConfig, vector_index: VectorIndexState) -> None:
        self._config = config
        self._vector_index = vector_index
        logger.info("Модель LLM (ответ бота): %s", config.llm_model)
        logger.info("Модель LLM (преобразование запроса): %s", config.llm_query_transform_model)
        self._llm_query = ChatOpenAI(
            model=config.llm_query_transform_model,
            api_key=config.open_api_key,
            base_url=config.open_base_url,
            temperature=0.4,
            max_tokens=512,
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

    async def ainvoke(self, messages: list[BaseMessage]) -> RagInvokeResult:
        store = self._vector_index.get_store()
        if store is None:
            logger.warning("RAG: vector store is missing")
            raise LlmInvocationError
        retriever = store.as_retriever(search_kwargs={"k": self._config.retriever_k})
        context_chain = (
            self._query_chain | retriever | RunnableLambda(_format_chunks)
        )
        chain = (
            RunnablePassthrough.assign(context=context_chain)
            | self._answer_prompt
            | self._llm_answer
            | StrOutputParser()
        )
        usage_cb = UsageMetadataCallbackHandler()
        try:
            out = await chain.ainvoke(
                {"messages": messages},
                config={"callbacks": [usage_cb]},
            )
        except APIStatusError as e:
            if e.status_code == 402:
                logger.warning("RAG LLM insufficient credits (HTTP 402)")
                raise LlmInsufficientCreditsError from None
            logger.warning("RAG LLM API status error: %s", e.status_code)
            raise LlmInvocationError from None
        except Exception as e:
            if is_insufficient_credits_error(e):
                logger.warning("RAG LLM insufficient credits (%s)", type(e).__name__)
                raise LlmInsufficientCreditsError from None
            logger.warning("RAG chain failed: %s", type(e).__name__)
            raise LlmInvocationError from None

        text = (out or "").strip()
        if not text:
            logger.warning("RAG returned empty assistant message")
            raise LlmInvocationError
        pin, pout, ptot = _aggregate_llm_usage(usage_cb)
        return RagInvokeResult(
            text=text,
            prompt_tokens=pin,
            completion_tokens=pout,
            total_tokens_turn=ptot,
        )
