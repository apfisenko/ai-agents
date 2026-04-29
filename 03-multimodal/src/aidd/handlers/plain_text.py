import asyncio
from datetime import timezone

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from aidd.conversation_store import ConversationStore
from aidd.llm_client import LlmClient, LlmInvocationError
from aidd.transaction_store import TransactionStore, records_from_extracted

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


async def _typing_while_waiting(bot: Bot, chat_id: int) -> None:
    """Периодически отправляет «печатает…», пока активна задача (LLM может отвечать долго)."""
    try:
        while True:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4.0)
    except asyncio.CancelledError:
        raise


def _fallback_date_from_message(message: Message):
    """Дата операции по умолчанию — календарный день UTC времени сообщения Telegram."""
    when = message.date
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).date()


@router.message(F.text)
async def plain_text(
    message: Message,
    conversation_store: ConversationStore,
    transaction_store: TransactionStore,
    llm_client: LlmClient,
    system_prompt: str,
    default_currency: str,
) -> None:
    chat_id = message.chat.id
    text = message.text or ""
    history = conversation_store.get_messages(chat_id)
    messages = [*history, {"role": "user", "content": text}]
    typing_task = asyncio.create_task(_typing_while_waiting(message.bot, chat_id))
    try:
        try:
            extraction = await llm_client.extract_transactions(system_prompt, messages)
        except LlmInvocationError:
            await message.answer(_LLM_UNAVAILABLE)
            return
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    fb_date = _fallback_date_from_message(message)
    rows = records_from_extracted(extraction.transactions, fb_date, default_currency)
    transaction_store.add_many(chat_id, rows)

    reply = (extraction.reply_to_user or "").strip()
    if not reply:
        if rows:
            n = len(rows)
            reply = f"Записано операций: {n}. Спрашивайте /balance для сводки."
        else:
            reply = "Опишите трату или доход суммой — сохраню в учёт или отвечу по теме финансов."

    conversation_store.add_exchange(chat_id, text, reply)
    parts = _split_text_for_telegram(reply)
    await message.answer(parts[0])
    for chunk in parts[1:]:
        await message.answer(chunk)
