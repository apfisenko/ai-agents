from aiogram import F, Router
from aiogram.types import Message

router = Router()

# Единая политика нетекстовых сообщений: короткое нейтральное уведомление
_NON_TEXT_HINT = "Пока обрабатываю только обычный текст. Пожалуйста, пришлите сообщение как текст."


@router.message(~F.text)
async def handle_non_text(message: Message) -> None:
    await message.answer(_NON_TEXT_HINT)
