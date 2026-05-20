"""Отправка пользователю результата хода банковского агента (ответ + источники + статистика)."""

from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot
from aiogram.enums import ChatAction, ParseMode
from aiogram.types import Message

from aidd.bank_agent import BankAgentTurnResult
from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.pii_outgoing import maybe_mask_outgoing_pan
from aidd.rag_chain import format_sources_for_user

logger = logging.getLogger(__name__)

_TELEGRAM_MAX_MESSAGE_LENGTH = 4096


async def typing_while_waiting(bot: Bot, chat_id: int) -> None:
    """Периодически отправляет «печатает…», пока активна задача (LLM может отвечать долго)."""
    try:
        while True:
            try:
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
            except Exception:
                logger.debug("send_chat_action (typing) failed", exc_info=True)
            await asyncio.sleep(4.0)
    except asyncio.CancelledError:
        raise


def split_text_for_telegram(text: str) -> list[str]:
    """Разбивает текст на части по лимиту Telegram без падения отправки."""
    if len(text) <= _TELEGRAM_MAX_MESSAGE_LENGTH:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        chunks.append(rest[:_TELEGRAM_MAX_MESSAGE_LENGTH])
        rest = rest[_TELEGRAM_MAX_MESSAGE_LENGTH:]
    return chunks


def format_usage_stats_table_html(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    session_total_tokens: int,
    success: bool,
) -> str:
    """Табличное представление статистики LLM для Telegram (HTML + pre)."""
    ok_text = "да" if success else "нет"
    rows = [
        ("Модель LLM", model),
        ("Передано token", str(prompt_tokens)),
        ("Получено token", str(completion_tokens)),
        ("Всего token в сессии", str(session_total_tokens)),
        ("Успешность запроса", ok_text),
    ]
    label_w = 26
    lines = [f"{label:<{label_w}} {value}" for label, value in rows]
    block = "\n".join(lines)
    return f"<pre>{html.escape(block)}</pre>"


async def send_bank_turn_result_followup(
    anchor: Message,
    rag_result: BankAgentTurnResult,
    *,
    conversation_store: ConversationStore,
    app_config: AppConfig,
) -> None:
    """Сообщает результат завершённого хода чата после якорного сообщения (текущий текст / callback)."""
    chat_id = anchor.chat.id
    logger.info("bank_turn_reply: chat_id=%s reply_len=%s", chat_id, len(rag_result.text))
    answer_body = rag_result.text
    reply_for_user = answer_body
    if app_config.show_sources:
        src = format_sources_for_user(rag_result.documents)
        if src:
            reply_for_user = f"{answer_body}\n\n📚 Источники: {src}"
    reply_for_user = maybe_mask_outgoing_pan(
        reply_for_user, enabled=app_config.mask_pan_outgoing
    )
    session_tokens_total = conversation_store.add_session_llm_total_tokens(
        chat_id, rag_result.total_tokens_turn
    )
    parts = split_text_for_telegram(reply_for_user)
    await anchor.answer(parts[0])
    for chunk in parts[1:]:
        await anchor.answer(chunk)
    stats_html = format_usage_stats_table_html(
        model=app_config.llm_model,
        prompt_tokens=rag_result.prompt_tokens,
        completion_tokens=rag_result.completion_tokens,
        session_total_tokens=session_tokens_total,
        success=not rag_result.used_fallback,
    )
    await anchor.answer(stats_html, parse_mode=ParseMode.HTML)
