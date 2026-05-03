import asyncio
import html

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.types import Message

from langchain_core.messages import HumanMessage

from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.llm_client import (
    LlmInsufficientCreditsError,
    LlmInvocationError,
    TELEGRAM_REPLY_INSUFFICIENT_CREDITS,
)
from aidd.rag_chain import RagChainRunner

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
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4.0)
    except asyncio.CancelledError:
        raise


@router.message(F.text)
async def plain_text(
    message: Message,
    conversation_store: ConversationStore,
    rag_runner: RagChainRunner,
    app_config: AppConfig,
) -> None:
    chat_id = message.chat.id
    text = message.text or ""
    history = conversation_store.get_messages(chat_id)
    messages = [*history, HumanMessage(content=text)]
    typing_task = asyncio.create_task(_typing_while_waiting(message.bot, chat_id))
    try:
        try:
            rag_result = await rag_runner.ainvoke(messages)
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

    reply = rag_result.text
    conversation_store.append_user_message(chat_id, text)
    conversation_store.append_assistant_message(chat_id, reply)
    session_tokens_total = conversation_store.add_session_llm_total_tokens(
        chat_id, rag_result.total_tokens_turn
    )
    parts = _split_text_for_telegram(reply)
    await message.answer(parts[0])
    for chunk in parts[1:]:
        await message.answer(chunk)
    stats_html = _format_usage_stats_table_html(
        model=app_config.llm_model,
        prompt_tokens=rag_result.prompt_tokens,
        completion_tokens=rag_result.completion_tokens,
        session_total_tokens=session_tokens_total,
        success=True,
    )
    await message.answer(stats_html, parse_mode=ParseMode.HTML)
