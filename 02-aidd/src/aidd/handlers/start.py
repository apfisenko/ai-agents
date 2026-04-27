from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

_START_GREETING = "Привет! Бот в режиме обкатки: доступна команда /start; остальное — в следующих версиях."


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(_START_GREETING)
