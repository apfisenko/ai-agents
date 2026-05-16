import asyncio
import html
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.types import Message

from aidd.bank_agent import BankAgentRunner
from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.llm_client import (
    LlmInsufficientCreditsError,
    LlmInvocationError,
    TELEGRAM_REPLY_INSUFFICIENT_CREDITS,
)
from aidd.rag_chain import format_sources_for_user

logger = logging.getLogger(__name__)

router = Router()

_LLM_UNAVAILABLE = "Сервис временно недоступен. Попробуйте позже."

# Telegram Bot API: длина одного сообщения (символы Юникода в Python str).
_TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def _split_text_for_telegram(text: str) -> list[str]:
    """Разбивает текст на части по лимиту Telegram без падения отправки."""
    if len(text) <= _TELEGRAM_MAX_MESSAGE_LENGTH:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        chunks.append(rest[:_TELEGRAM_MAX_MESSAGE_LENGTH])
        rest = rest[_TELEGRAM_MAX_MESSAGE_LENGTH :]
    return chunks


def _format_usage_stats_table_html(
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


async def _typing_while_waiting(bot: Bot, chat_id: int) -> None:
    """Периодически отправляет «печатает…», пока активна задача (LLM может отвечать долго)."""
    try:
        while True:
            try:
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
            except Exception:
                # Не даём упасть фоновой задаче: иначе await в finally обрывает отправку ответа.
                logger.debug("send_chat_action (typing) failed", exc_info=True)
            await asyncio.sleep(4.0)
    except asyncio.CancelledError:
        raise


@router.message(F.text)
async def plain_text(
    message: Message,
    conversation_store: ConversationStore,
    bank_runner: BankAgentRunner,
    app_config: AppConfig,
) -> None:
    chat_id = message.chat.id
    text = message.text or ""
    logger.info("plain_text: chat_id=%s user_len=%s", chat_id, len(text))
    typing_task = asyncio.create_task(_typing_while_waiting(message.bot, chat_id))
    try:
        try:
            rag_result = await bank_runner.ainvoke_turn(chat_id=chat_id, user_text=text)
        except LlmInsufficientCreditsError:
            await message.answer(TELEGRAM_REPLY_INSUFFICIENT_CREDITS)
            return
        except LlmInvocationError:
            await message.answer(_LLM_UNAVAILABLE)
            return
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("typing task finished with error after cancel", exc_info=True)

    logger.info("plain_text: LLM готов, chat_id=%s reply_len=%s", chat_id, len(rag_result.text))
    answer_body = rag_result.text
    reply_for_user = answer_body
    if app_config.show_sources:
        src = format_sources_for_user(rag_result.documents)
        if src:
            reply_for_user = f"{answer_body}\n\n📚 Источники: {src}"
    session_tokens_total = conversation_store.add_session_llm_total_tokens(
        chat_id, rag_result.total_tokens_turn
    )
    parts = _split_text_for_telegram(reply_for_user)
    await message.answer(parts[0])
    for chunk in parts[1:]:
        await message.answer(chunk)
    stats_html = _format_usage_stats_table_html(
        model=app_config.llm_model,
        prompt_tokens=rag_result.prompt_tokens,
        completion_tokens=rag_result.completion_tokens,
        session_total_tokens=session_tokens_total,
        success=not rag_result.used_fallback,
    )
    await message.answer(stats_html, parse_mode=ParseMode.HTML)
