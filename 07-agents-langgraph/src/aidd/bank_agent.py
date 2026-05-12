"""ReAct-агент банковского сценария: `create_agent` + in-memory checkpointer (LangGraph `InMemorySaver`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langchain.agents import create_agent
from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from openai import APIStatusError

from aidd.agent_sources import documents_from_rag_tool_turn
from aidd.config import AppConfig
from aidd.indexed_retrieval import IndexedRetriever
from aidd.llm_client import (
    LlmInsufficientCreditsError,
    LlmInvocationError,
    is_insufficient_credits_error,
)
from aidd.tools.rag_search_tool import make_rag_search_tool

logger = logging.getLogger(__name__)


def wipe_in_memory_thread(checkpointer: InMemorySaver, thread_id: str) -> None:
    """Сброс состояния LangGraph для thread_id (совместимо с `InMemorySaver` 1.x)."""
    tid = str(thread_id)
    checkpointer.storage.pop(tid, None)
    for k in list(checkpointer.writes.keys()):
        if k[0] == tid:
            del checkpointer.writes[k]
    for k in list(checkpointer.blobs.keys()):
        if k[0] == tid:
            del checkpointer.blobs[k]


def _aggregate_llm_usage(cb: UsageMetadataCallbackHandler) -> tuple[int, int, int]:
    inp = out = tot = 0
    for meta in cb.usage_metadata.values():
        inp += int(meta.get("input_tokens") or 0)
        out += int(meta.get("output_tokens") or 0)
        tot += int(meta.get("total_tokens") or 0)
    if tot <= 0 and (inp + out) > 0:
        tot = inp + out
    return inp, out, tot


def _flatten_ai_content(msg: AIMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _final_turn_assistant_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if not isinstance(m, AIMessage):
            continue
        tc = getattr(m, "tool_calls", None) or []
        if tc:
            continue
        return _flatten_ai_content(m)
    return ""


@dataclass(frozen=True)
class BankAgentTurnResult:
    """Текст финального ответа, usage и документы из `rag_search` за текущий запрос."""

    text: str
    documents: tuple[Document, ...]
    prompt_tokens: int
    completion_tokens: int
    total_tokens_turn: int


class BankAgentRunner:
    def __init__(self, agent_graph: Any, checkpointer: InMemorySaver) -> None:
        self._agent = agent_graph
        self._checkpointer = checkpointer

    @classmethod
    def build(
        cls,
        config: AppConfig,
        indexed: IndexedRetriever,
        *,
        checkpointer: InMemorySaver | None = None,
    ) -> BankAgentRunner:
        llm = ChatOpenAI(
            model=config.llm_model,
            api_key=config.open_api_key,
            base_url=config.open_base_url,
            temperature=0.7,
            max_tokens=config.llm_max_completion_tokens,
        )
        rag_tool = make_rag_search_tool(indexed)
        saver = checkpointer or InMemorySaver()
        agent_graph = create_agent(
            llm,
            tools=[rag_tool],
            system_prompt=config.system_prompt_text,
            checkpointer=saver,
        )
        return cls(agent_graph, saver)

    def reset_thread(self, chat_id: int) -> None:
        wipe_in_memory_thread(self._checkpointer, str(chat_id))

    async def ainvoke_turn(self, *, chat_id: int, user_text: str) -> BankAgentTurnResult:
        usage_cb = UsageMetadataCallbackHandler()
        cfg_runnable: dict[str, Any] = {
            "configurable": {"thread_id": str(chat_id)},
            "callbacks": [usage_cb],
        }
        try:
            out = await self._agent.ainvoke(
                {"messages": [HumanMessage(content=user_text)]},
                config=cfg_runnable,
            )
        except Exception as exc:
            if isinstance(exc, APIStatusError):
                if exc.status_code == 402:
                    raise LlmInsufficientCreditsError() from exc
                logger.warning("Bank agent APIStatusError: %s", exc.status_code)
                raise LlmInvocationError() from exc
            if is_insufficient_credits_error(exc):
                raise LlmInsufficientCreditsError() from exc
            logger.warning("Bank agent failed: %s: %s", type(exc).__name__, exc)
            raise LlmInvocationError() from exc

        msgs = out.get("messages") or []
        if not isinstance(msgs, list):
            msgs = list(msgs)
        text = _final_turn_assistant_text(msgs)
        docs_list = documents_from_rag_tool_turn(msgs)
        pin, pout, ptot = _aggregate_llm_usage(usage_cb)
        if not text:
            logger.warning("Bank agent: пустой финальный ответ ассистента")
            raise LlmInvocationError()

        return BankAgentTurnResult(
            text=text,
            documents=tuple(docs_list),
            prompt_tokens=pin,
            completion_tokens=pout,
            total_tokens_turn=ptot,
        )
