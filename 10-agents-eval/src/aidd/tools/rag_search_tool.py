"""Инструмент `rag_search`: поиск по локальному индексу, JSON с ключом `sources` (vision §8)."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from aidd.indexed_retrieval import IndexedRetriever, documents_to_sources_payload
from aidd.llm_client import LlmInsufficientCreditsError, LlmInvocationError

logger = logging.getLogger(__name__)

RAG_SEARCH_TOOL_NAME = "rag_search"

_RAG_SEARCH_DESCRIPTION = (
    "Ищет в локальных справочных документах банка по формулировке запроса (русский или смешанный язык). "
    "Вызывай для фактов о продуктах, ставках, сроках, условиях вкладов и кредитов из базы данных бота — "
    "не для общих разговоров и не для выдумывания цифр. "
    "Переформулируй вопрос в поисковую строку с ключевыми терминами; при ответе пользователю опирайся на "
    "поле page_content каждого элемента в sources."
)


def make_rag_search_tool(retriever: IndexedRetriever):
    """Возвращает зарегистрированный tool (замыкание на один экземпляр IndexedRetriever)."""

    @tool(RAG_SEARCH_TOOL_NAME, description=_RAG_SEARCH_DESCRIPTION)
    async def rag_search(
        search_query: Annotated[
            str,
            (
                "Поисковая фраза по смыслу вопроса пользователя "
                "(синонимы, официальные названия продуктов, ключевые слова)."
            ),
        ],
    ) -> str:
        try:
            documents = await retriever.aretrieve(search_query)
        except LlmInsufficientCreditsError:
            logger.warning("rag_search: insufficient credits during retrieval")
            return json.dumps({"sources": []}, ensure_ascii=False)
        except LlmInvocationError:
            logger.warning("rag_search: retrieval failed")
            return json.dumps({"sources": []}, ensure_ascii=False)
        except Exception:
            logger.exception("rag_search: unexpected error")
            return json.dumps({"sources": []}, ensure_ascii=False)

        payload = documents_to_sources_payload(documents)
        logger.debug(
            "rag_search: query_preview=%s docs=%d mode=%s",
            (search_query[:80] + "…") if len(search_query) > 80 else search_query,
            len(payload),
            retriever.rag_retrieval_mode,
        )
        return json.dumps({"sources": payload}, ensure_ascii=False)

    return rag_search
