"""Документы из ответа агента: ToolMessage `rag_search` после последнего HumanMessage (vision §8)."""

from __future__ import annotations

import json
import logging
from typing import Sequence

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from aidd.tools.rag_search_tool import RAG_SEARCH_TOOL_NAME

logger = logging.getLogger(__name__)


def documents_from_rag_tool_turn(messages: Sequence[BaseMessage]) -> list[Document]:
    """Собирает чанки из JSON `rag_search` с конца истории, начиная после последнего HumanMessage."""
    msgs = list(messages)
    last_human = -1
    for i, m in enumerate(msgs):
        if isinstance(m, HumanMessage):
            last_human = i
    if last_human < 0:
        return []

    out: list[Document] = []
    for m in msgs[last_human + 1 :]:
        if not isinstance(m, ToolMessage):
            continue
        if (m.name or "") != RAG_SEARCH_TOOL_NAME:
            continue
        raw = m.content
        if not isinstance(raw, str):
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Не удалось распарсить JSON от инструмента %s", RAG_SEARCH_TOOL_NAME)
            continue
        sources = data.get("sources")
        if not isinstance(sources, list):
            continue
        for item in sources:
            if not isinstance(item, dict):
                continue
            fn = str(item.get("source") or "unknown")
            text = str(item.get("page_content") or "")
            meta: dict[str, str | int] = {"source": fn}
            page = item.get("page")
            if isinstance(page, int):
                meta["page"] = max(page - 1, 0)
            out.append(Document(page_content=text, metadata=meta))
    return out
