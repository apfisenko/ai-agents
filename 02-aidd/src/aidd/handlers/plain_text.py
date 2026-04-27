import asyncio

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from aidd.conversation_store import ConversationStore
from aidd.llm_client import LlmClient, LlmInvocationError

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


@router.message(F.text)
async def plain_text(
    message: Message,
    conversation_store: ConversationStore,
    llm_client: LlmClient,
    system_prompt: str,
) -> None:
    chat_id = message.chat.id
    text = message.text or ""
    history = conversation_store.get_messages(chat_id)
    messages = [*history, {"role": "user", "content": text}]
    typing_task = asyncio.create_task(_typing_while_waiting(message.bot, chat_id))
    try:
        try:
            reply = await llm_client.complete(system_prompt, messages)
        except LlmInvocationError:
            await message.answer(_LLM_UNAVAILABLE)
            return
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    conversation_store.add_exchange(chat_id, text, reply)
    parts = _split_text_for_telegram(reply)
    await message.answer(parts[0])
    for chunk in parts[1:]:
        await message.answer(chunk)
