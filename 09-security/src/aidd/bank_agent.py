"""ReAct-агент банковского сценария: `create_agent` + in-memory checkpointer (LangGraph `InMemorySaver`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, Interrupt
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

# MCP-инструменты с human-in-the-loop (vision §12): только approve/reject.
_HITL_INTERRUPT_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "open_credit_card": {
        "allowed_decisions": ["approve", "reject"],
        "description": (
            "Эмуляция открытия кредитной карты (MCP open_credit_card). "
            "Подтверждайте только если пользователь явно согласен на демо-операцию."
        ),
    },
    "open_deposit": {
        "allowed_decisions": ["approve", "reject"],
        "description": (
            "Эмуляция открытия вклада (MCP open_deposit). "
            "Подтверждайте только если пользователь явно согласен на демо-операцию."
        ),
    },
}

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

    middleware: list[Any] = []
    interrupt_on: dict[str, Any] = {
        name: spec for name, spec in _HITL_INTERRUPT_TOOL_SPECS.items() if name in mcp_tool_names
    }
    if interrupt_on:
        middleware.append(
            HumanInTheLoopMiddleware(
                interrupt_on=interrupt_on,
                description_prefix="Требуется подтверждение операции",
            )
        )
        logger.info(
            "HITL: HumanInTheLoopMiddleware для инструментов: %s",
            ", ".join(sorted(interrupt_on)),
        )

    saver = checkpointer or InMemorySaver()
    agent_graph = create_agent(
        llm,
        tools=tools,
        system_prompt=config.system_prompt_text,
        checkpointer=saver,
        middleware=middleware,
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


def _interrupts_from_stream_update(update: Any) -> list[Interrupt]:
    """Из значения ключа ``__interrupt__`` в chunk LangGraph ``astream(..., stream_mode='updates')``."""
    found: list[Interrupt] = []
    if isinstance(update, tuple):
        for item in update:
            if isinstance(item, Interrupt):
                found.append(item)
    elif isinstance(update, list):
        for item in update:
            if isinstance(item, Interrupt):
                found.append(item)
    elif isinstance(update, Interrupt):
        found.append(update)
    return found


def format_hitl_prompt_for_user(interrupt: Interrupt) -> str:
    """Текст для пользователя до подтверждения HITL вместе с inline Accept / Reject в Telegram."""
    val = interrupt.value
    lines = [
        "Нужно ваше подтверждение по операции в банке (демо-режим).",
        "",
    ]
    if isinstance(val, dict):
        reqs = val.get("action_requests") or []
        if reqs and isinstance(reqs[0], dict):
            ar0 = reqs[0]
            name = ar0.get("name", "?")
            args = ar0.get("args", {})
            desc = ar0.get("description") or ""
            lines.append(f"Инструмент: {name}")
            lines.append(f"Параметры: {args}")
            if desc:
                lines.append("")
                lines.append(str(desc))
        else:
            lines.append(str(val))
    else:
        lines.append(str(val))
    lines.extend(
        [
            "",
            "Нажмите Accept чтобы выполнить операцию или Reject чтобы отменить.",
            "Можно также ответить коротко: «ДА» / подтверждаю или «НЕТ» / отмена.",
        ]
    )
    return "\n".join(lines)


@dataclass(frozen=True)
class BankAgentTurnResult:
    """Результат хода агента. При ``hitl_pending`` — следующий вызов с ``resume_command``."""

    text: str
    documents: tuple[Document, ...]
    prompt_tokens: int
    completion_tokens: int
    total_tokens_turn: int
    used_fallback: bool = False
    hitl_pending: bool = False
    hitl_user_prompt: str = ""


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
        self._hitl_waiting_threads: set[str] = set()

    def hitl_is_waiting(self, chat_id: int, thread_id: str | None = None) -> bool:
        tid = thread_id if thread_id is not None else str(chat_id)
        return tid in self._hitl_waiting_threads

    def reset_thread(self, chat_id: int) -> None:
        wipe_in_memory_thread(self._checkpointer, str(chat_id))
        self._hitl_waiting_threads.discard(str(chat_id))

    async def ainvoke_turn(
        self,
        *,
        chat_id: int,
        user_text: str | None = None,
        thread_id: str | None = None,
        resume_command: Command | None = None,
    ) -> BankAgentTurnResult:
        """Ход агента через ``astream`` (паттерн ``run_turn_agent`` из ``data/agent-guards-demo.ipynb``).

        Либо новое сообщение пользователя (``user_text``), либо ``resume_command`` после HITL —
        не оба сразу.
        Для оценки на датасете передайте ``thread_id`` — изоляция MemorySaver между примерами.
        """
        if (user_text is None and resume_command is None) or (
            user_text is not None and resume_command is not None
        ):
            raise ValueError("Задайте ровно одно из полей: user_text или resume_command")

        tid = thread_id if thread_id is not None else str(chat_id)
        usage_cb = UsageMetadataCallbackHandler()
        cfg_runnable: dict[str, Any] = {
            "configurable": {"thread_id": tid},
            "callbacks": [usage_cb],
        }

        if resume_command is not None:
            input_payload: dict[str, Any] | Command = resume_command
        else:
            ut = (user_text or "").strip()
            if not ut:
                raise ValueError("user_text не может быть пустым")
            input_payload = {"messages": [HumanMessage(content=ut)]}

        interrupts: list[Interrupt] = []
        step_idx = 0
        try:
            async for step in self._agent.astream(
                input_payload,
                config=cfg_runnable,
                stream_mode="updates",
            ):
                if not isinstance(step, dict):
                    continue
                for node_name, update in step.items():
                    if node_name == "__interrupt__":
                        batch = _interrupts_from_stream_update(update)
                        for intr in batch:
                            interrupts.append(intr)
                            logger.info(
                                "Bank agent HITL interrupt id=%s pending_confirmations=%d",
                                getattr(intr, "id", "?"),
                                len(interrupts),
                            )
                        continue
                    if isinstance(update, dict):
                        raw_m = update.get("messages")
                        if isinstance(raw_m, list) and raw_m:
                            log_bank_agent_stream_step(step_idx, raw_m)
                            step_idx += 1
                            for m in raw_m:
                                if isinstance(m, AIMessage):
                                    tc = getattr(m, "tool_calls", None) or []
                                    if not tc and not _flatten_ai_content(m):
                                        logger.warning("Bank agent: пустой AIMessage без tool_calls")

            snap = await self._agent.aget_state(cfg_runnable)
            vals = snap.values
            raw_msgs = vals.get("messages") if isinstance(vals, dict) else None
            msgs_final = list(raw_msgs or [])
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

        log_mcp_bank_tool_calls(msgs_final, self._mcp_tool_names)

        pin, pout, ptot = _aggregate_llm_usage(usage_cb)

        if interrupts:
            self._hitl_waiting_threads.add(tid)
            intr0 = interrupts[0]
            prompt_txt = format_hitl_prompt_for_user(intr0)
            return BankAgentTurnResult(
                text="",
                documents=tuple(),
                prompt_tokens=pin,
                completion_tokens=pout,
                total_tokens_turn=ptot,
                used_fallback=False,
                hitl_pending=True,
                hitl_user_prompt=prompt_txt,
            )

        self._hitl_waiting_threads.discard(tid)

        text = _final_turn_assistant_text(msgs_final)
        docs_list = documents_from_rag_tool_turn(msgs_final)
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
            hitl_pending=False,
            hitl_user_prompt="",
        )
