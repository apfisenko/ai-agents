from aiogram import F, Router
from aiogram.types import Message

from aidd.conversation_store import ConversationStore
from aidd.llm_client import LlmClient, LlmInvocationError

router = Router()

_LLM_UNAVAILABLE = "Сервис временно недоступен. Попробуйте позже."


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
    try:
        reply = await llm_client.complete(system_prompt, messages)
    except LlmInvocationError:
        await message.answer(_LLM_UNAVAILABLE)
        return
    conversation_store.add_exchange(chat_id, text, reply)
    await message.answer(reply)
