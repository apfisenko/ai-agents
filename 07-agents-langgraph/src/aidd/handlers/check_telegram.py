from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("check_telegram"))
async def cmd_check_telegram(message: Message, bot: Bot) -> None:
    me = await bot.get_me()
    uname = f"@{me.username}" if me.username else "—"
    await message.answer(
        f"Связь с Telegram API в порядке. Бот: {uname}, id={me.id}."
    )
