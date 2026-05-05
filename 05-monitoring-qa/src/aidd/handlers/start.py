from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.conversation_store import ConversationStore

router = Router()

_START_GREETING = (
    "Привет! Я Помогальник — справочный ассистент по документам из каталога data "
    "(вклады, кредит, тексты справки): ответы строятся через поиск по фрагментам и модель. "
    "История чата в памяти до перезапуска; /start сбрасывает контекст этого чата. "
    "Команды: /index_status — число фрагментов в индексе; /index — переиндексация; "
    "/evaluate_dataset — оценка датасета RAGAS → LangSmith feedback (нужен LangSmith). "
    "/check_telegram — проверка связи с Telegram API."
)


@router.message(Command("start"))
async def cmd_start(message: Message, conversation_store: ConversationStore) -> None:
    conversation_store.clear(message.chat.id)
    await message.answer(_START_GREETING)
