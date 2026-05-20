from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.bank_agent import BankAgentRunner
from aidd.conversation_store import ConversationStore

router = Router()

_START_GREETING = (
    "Привет! Я Помогальник — справочный ассистент по банковским материалам из локальной базы "
    "(вклады, кредит, тексты справки): ответ через ReAct-агента; при запросах о фактах из базы используется поиск rag_search. "
    "История чата в памяти до перезапуска процесса; /start очищает контекст чата здесь же. "
    "Команды: /index_status — число фрагментов в индексе; /index — переиндексация; "
    "/mcp_status — доступен ли MCP-сервер банка и список инструментов (см. make check-mcp-bank); "
    "/evaluate_dataset — оценка датасета RAGAS → LangSmith feedback (нужен LangSmith). "
    "/check_telegram — проверка связи с Telegram API."
)


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    conversation_store: ConversationStore,
    bank_runner: BankAgentRunner,
) -> None:
    conversation_store.clear(message.chat.id)
    bank_runner.reset_thread(message.chat.id)
    await message.answer(_START_GREETING)
