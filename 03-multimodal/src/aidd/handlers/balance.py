from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.transaction_store import TransactionStore, format_balance_report

router = Router()


@router.message(Command("balance"))
async def cmd_balance(message: Message, transaction_store: TransactionStore) -> None:
    rows = transaction_store.get_all(message.chat.id)
    await message.answer(format_balance_report(rows))
