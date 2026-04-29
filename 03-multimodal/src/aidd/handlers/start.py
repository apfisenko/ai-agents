from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.conversation_store import ConversationStore
from aidd.transaction_store import TransactionStore

router = Router()

_START_GREETING = (
    "Привет! Я Помогальник — персональный финансовый советник: помогаю вести учёт доходов и расходов "
    "из текста и по фото чеков. Пишите суммы и описание — я распознаю операции; команда "
    "/balance — сводка из памяти до перезапуска бота. При /start контекст этого чата и учёт "
    "сбрасываются. Команда /check_telegram — проверка связи с Telegram API."
)


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    conversation_store: ConversationStore,
    transaction_store: TransactionStore,
) -> None:
    cid = message.chat.id
    conversation_store.clear(cid)
    transaction_store.clear(cid)
    await message.answer(_START_GREETING)
