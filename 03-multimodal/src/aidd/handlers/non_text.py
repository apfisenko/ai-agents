from aiogram import F, Router
from aiogram.types import Message

router = Router()

# Единая политика нетекстовых сообщений: короткое нейтральное уведомление
_NON_TEXT_HINT = (
    "Этот тип сообщения пока не поддерживаю. Пришлите текст, голосовое сообщение или фото чека."
)


@router.message(~F.text)
async def handle_non_text(message: Message) -> None:
    await message.answer(_NON_TEXT_HINT)
