from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.conversation_store import ConversationStore

router = Router()

_START_GREETING = (
    "Привет! Я Помогальник: отвечаю на текстовые сообщения через модель. "
    "История чата в памяти до перезапуска бота; при /start контекст этого чата сбрасывается. "
    "Команда /check_telegram — проверка связи с Telegram API."
)


@router.message(Command("start"))
async def cmd_start(message: Message, conversation_store: ConversationStore) -> None:
    conversation_store.clear(message.chat.id)
    await message.answer(_START_GREETING)
