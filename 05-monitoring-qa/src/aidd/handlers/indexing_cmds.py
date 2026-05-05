import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.config import AppConfig
from aidd.llm_client import TELEGRAM_REPLY_INSUFFICIENT_CREDITS, is_insufficient_credits_error
from aidd.vector_index import VectorIndexState

logger = logging.getLogger(__name__)

router = Router()

_INDEX_FAIL_USER = "Не удалось выполнить переиндексацию. Попробуйте позже."


@router.message(Command("index"))
async def cmd_index(
    message: Message,
    app_config: AppConfig,
    vector_index: VectorIndexState,
) -> None:
    try:
        await asyncio.to_thread(vector_index.rebuild_from_config, app_config)
    except Exception as e:
        logger.exception("Manual /index failed")
        if is_insufficient_credits_error(e):
            await message.answer(TELEGRAM_REPLY_INSUFFICIENT_CREDITS)
        else:
            await message.answer(_INDEX_FAIL_USER)
        return
    await message.answer(
        f"Переиндексация завершена. Чанков в индексе: {vector_index.chunk_count}."
    )


@router.message(Command("index_status"))
async def cmd_index_status(
    message: Message,
    vector_index: VectorIndexState,
) -> None:
    n = vector_index.chunk_count
    await message.answer(f"Статус индекса: готов. Чанков: {n}.")
