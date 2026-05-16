"""ReAct-агент банковского сценария: `create_agent` + in-memory checkpointer (LangGraph `InMemorySaver`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
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
from aidd.tools.currency_convert_tool import make_convert_currency_tool
from aidd.tools.rag_search_tool import make_rag_search_tool

logger = logging.getLogger(__name__)

# Короткий нейтральный текст при пустом финальном ответе модели (vision §8).
FALLBACK_ASSISTANT_REPLY = (
    "Сейчас не удалось подготовить ответ. Переформулируйте вопрос или попробуйте позже."
)

_MCP_SERVER_NAME = "bank"


def _mcp_tool_names_frozen(mcp_tools: Sequence[Any]) -> frozenset[str]:
    """Имена инструментов с MCP-сервера, как сообщает клиент после ``get_tools()``."""
    names: set[str] = set()
    for t in mcp_tools:
        raw = getattr(t, "name", None)
        if isinstance(raw, str):
            s = raw.strip()
            if s:
                names.add(s)
    return frozenset(names)


async def create_bank_agent(
    config: AppConfig,
    indexed: IndexedRetriever,
    *,
    checkpointer: InMemorySaver | None = None,
) -> tuple[Any, InMemorySaver, frozenset[str]]:
    """Собирает граф агента и in-memory checkpointer. MCP-инструменты — при успешном ``get_tools()``.

    Имена MCP-инструментов для логов хода диалога — из того же списка, что вернул ``get_tools()``;
    если MCP недоступен или отключён — пустое ``frozenset``.
    """
    llm = ChatOpenAI(
        model=config.llm_model,
        api_key=config.open_api_key,
        base_url=config.open_base_url,
        temperature=0.7,
        max_tokens=config.llm_max_completion_tokens,
    )
    rag_tool = make_rag_search_tool(indexed)
    currency_tool = make_convert_currency_tool()
    tools: list[Any] = [rag_tool, currency_tool]
    mcp_tool_names: frozenset[str] = frozenset()

    if config.mcp_bank_enabled:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            mcp_client = MultiServerMCPClient(
                {
                    _MCP_SERVER_NAME: {
                        "transport": "streamable_http",
                        "url": config.mcp_bank_streamable_http_url,
                    }
                }
            )
            mcp_tools = await mcp_client.get_tools()
            tools.extend(mcp_tools)
            mcp_tool_names = _mcp_tool_names_frozen(mcp_tools)
            mcp_names_ordered = sorted(mcp_tool_names)
            logger.info(
                "MCP bank: подключено инструментов %d (%s): %s",
                len(mcp_tools),
                config.mcp_bank_streamable_http_url,
                ", ".join(mcp_names_ordered) if mcp_names_ordered else "(нет имён)",
            )
        except Exception as exc:
            logger.warning(
                "MCP bank недоступен по адресу %s, продолжаем без MCP-инструментов: %s: %s",
                config.mcp_bank_streamable_http_url,
                type(exc).__name__,
                exc,
            )
    else:
        logger.info("MCP bank отключён (MCP_BANK_ENABLED=false)")

    saver = checkpointer or InMemorySaver()
    agent_graph = create_agent(
        llm,
        tools=tools,
        system_prompt=config.system_prompt_text,
        checkpointer=saver,
    )
    return agent_graph, saver, mcp_tool_names


async def initialize_agent(
    config: AppConfig,
    indexed: IndexedRetriever,
    *,
    checkpointer: InMemorySaver | None = None,
) -> BankAgentRunner:
    """Async-обёртка над ``create_bank_agent`` → ``BankAgentRunner`` (итерация 23)."""
    graph, saver, mcp_tool_names = await create_bank_agent(
        config, indexed, checkpointer=checkpointer
    )
    return BankAgentRunner(graph, saver, mcp_tool_names=mcp_tool_names)


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


def _tool_call_name(tc: Any) -> str | None:
    if isinstance(tc, dict):
        raw = tc.get("name")
        return str(raw) if raw is not None and str(raw) != "" else None
    raw = getattr(tc, "name", None)
    return str(raw) if raw is not None and str(raw) != "" else None


def _summarize_message_tail(m: BaseMessage) -> str:
    """Краткое описание сообщения для лога без содержимого и секретов."""
    cn = m.__class__.__name__
    if isinstance(m, AIMessage):
        tc = getattr(m, "tool_calls", None) or []
        names = [_tool_call_name(t) or "?" for t in tc]
        has_text = bool(_flatten_ai_content(m))
        return f"{cn}(tools={names},has_text={has_text})"
    if isinstance(m, ToolMessage):
        return f"{cn}(name={m.name or '?'})"
    return cn


def _slice_after_last_human(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    msgs = list(messages)
    last = -1
    for i, m in enumerate(msgs):
        if isinstance(m, HumanMessage):
            last = i
    return msgs[last + 1 :] if last >= 0 else []


def log_mcp_bank_tool_calls(
    messages: Sequence[BaseMessage], mcp_tool_names: frozenset[str]
) -> None:
    """Явное логирование вызовов MCP по именам из ``get_tools()`` при старте бота."""
    if not mcp_tool_names:
        return
    for m in _slice_after_last_human(messages):
        if isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", None) or []:
                name = _tool_call_name(tc)
                if name and name in mcp_tool_names:
                    logger.info("MCP bank: запрошен инструмент name=%s", name)
        elif isinstance(m, ToolMessage):
            name = (m.name or "").strip()
            if name in mcp_tool_names:
                logger.info("MCP bank: получен результат инструмента name=%s", name)


def log_bank_agent_stream_step(step_idx: int, messages: Sequence[BaseMessage]) -> None:
    """Лог одного шага stream_mode values: длина истории и тип последнего сообщения."""
    msgs = list(messages)
    if not msgs:
        logger.info("bank_agent stream step=%d total_msgs=0", step_idx)
        return
    logger.info(
        "bank_agent stream step=%d total_msgs=%d tail=%s",
        step_idx,
        len(msgs),
        _summarize_message_tail(msgs[-1]),
    )


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
    used_fallback: bool = False


class BankAgentRunner:
    def __init__(
        self,
        agent_graph: Any,
        checkpointer: InMemorySaver,
        *,
        mcp_tool_names: frozenset[str] | None = None,
    ) -> None:
        self._agent = agent_graph
        self._checkpointer = checkpointer
        self._mcp_tool_names: frozenset[str] = mcp_tool_names or frozenset()

    def reset_thread(self, chat_id: int) -> None:
        wipe_in_memory_thread(self._checkpointer, str(chat_id))

    async def ainvoke_turn(
        self,
        *,
        chat_id: int,
        user_text: str,
        thread_id: str | None = None,
    ) -> BankAgentTurnResult:
        """Для оценки на датасете передайте ``thread_id`` — изоляция MemorySaver между примерами."""
        tid = thread_id if thread_id is not None else str(chat_id)
        usage_cb = UsageMetadataCallbackHandler()
        cfg_runnable: dict[str, Any] = {
            "configurable": {"thread_id": tid},
            "callbacks": [usage_cb],
        }
        last_out: dict[str, Any] | None = None
        try:
            # `ainvoke` надёжнее `astream(..., "values")`: в ряде версий стрим может не отдавать
            # финальное состояние или вести себя иначе, из‑за чего ответ в Telegram не отправляется.
            out = await self._agent.ainvoke(
                {"messages": [HumanMessage(content=user_text)]},
                config=cfg_runnable,
            )
            last_out = out if isinstance(out, dict) else None
            if last_out is not None:
                raw_msgs = last_out.get("messages") or []
                msgs = list(raw_msgs) if isinstance(raw_msgs, list) else list(raw_msgs)
                log_bank_agent_stream_step(0, msgs)
                for m in msgs:
                    if isinstance(m, AIMessage):
                        tc = getattr(m, "tool_calls", None) or []
                        if not tc and not _flatten_ai_content(m):
                            logger.warning("Bank agent: пустой AIMessage без tool_calls")
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

        if last_out is None:
            logger.warning("Bank agent: ainvoke вернул не dict; тип=%s", type(out).__name__)
            raise LlmInvocationError()

        msgs_final = last_out.get("messages") or []
        if not isinstance(msgs_final, list):
            msgs_final = list(msgs_final)
        log_mcp_bank_tool_calls(msgs_final, self._mcp_tool_names)
        text = _final_turn_assistant_text(msgs_final)
        docs_list = documents_from_rag_tool_turn(msgs_final)
        pin, pout, ptot = _aggregate_llm_usage(usage_cb)
        used_fallback = False
        if not text:
            logger.warning("Bank agent: пустой финальный ответ ассистента, показываем fallback")
            text = FALLBACK_ASSISTANT_REPLY
            used_fallback = True

        return BankAgentTurnResult(
            text=text,
            documents=tuple(docs_list),
            prompt_tokens=pin,
            completion_tokens=pout,
            total_tokens_turn=ptot,
            used_fallback=used_fallback,
        )
