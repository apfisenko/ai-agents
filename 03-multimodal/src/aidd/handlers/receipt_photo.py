"""Фото чека и документы-изображения → VLM → TransactionStore."""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from aiogram import Router
from aiogram.filters import BaseFilter
from aiogram.types import Message

from aidd.conversation_store import ConversationStore
from aidd.handlers.plain_text import (
    _LLM_UNAVAILABLE,
    _fallback_date_from_message,
    _split_text_for_telegram,
    _typing_while_waiting,
)
from aidd.llm_client import LlmClient, LlmInvocationError
from aidd.transaction_store import TransactionStore, records_from_extracted

logger = logging.getLogger(__name__)

router = Router()

# Скачивание крупного фото из Telegram может занимать больше дефолтных 30 с.
_TELEGRAM_FILE_DOWNLOAD_TIMEOUT = 120

_GENERIC_FAIL = (
    "Не удалось обработать фото. Попробуйте ещё раз или опишите трату текстом."
)


class PhotoOrImageDocument(BaseFilter):
    """Сжатое фото в чате или файл с MIME image/*."""

    async def __call__(self, message: Message) -> bool:
        if message.photo:
            return True
        d = message.document
        return bool(d and d.mime_type and d.mime_type.startswith("image/"))


@router.message(PhotoOrImageDocument())
async def receipt_image(
    message: Message,
    conversation_store: ConversationStore,
    transaction_store: TransactionStore,
    llm_client: LlmClient,
    system_prompt: str,
    default_currency: str,
) -> None:
    chat_id = message.chat.id
    typing_task = asyncio.create_task(
        _typing_while_waiting(message.bot, chat_id)
    )
    try:
        await _process_receipt_message(
            message,
            conversation_store,
            transaction_store,
            llm_client,
            system_prompt,
            default_currency,
        )
    except LlmInvocationError:
        await message.answer(_LLM_UNAVAILABLE)
    except Exception:
        logger.exception("Receipt handler failed")
        try:
            await message.answer(_GENERIC_FAIL)
        except Exception:
            logger.warning("Could not send receipt error reply to chat")
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


async def _process_receipt_message(
    message: Message,
    conversation_store: ConversationStore,
    transaction_store: TransactionStore,
    llm_client: LlmClient,
    system_prompt: str,
    default_currency: str,
) -> None:
    chat_id = message.chat.id
    buf = BytesIO()
    caption = (message.caption or "").strip()

    if message.photo:
        mime = "image/jpeg"
        file_ref = message.photo[-1]
    else:
        doc = message.document
        assert doc is not None
        mime = (doc.mime_type or "image/jpeg").strip()
        file_ref = doc

    try:
        await message.bot.download(
            file=file_ref,
            destination=buf,
            timeout=_TELEGRAM_FILE_DOWNLOAD_TIMEOUT,
        )
    except Exception as e:
        logger.warning("Telegram file download failed: %s", type(e).__name__)
        await message.answer(
            "Не удалось загрузить файл. Пришлите фото или изображение ещё раз."
        )
        return

    raw = buf.getvalue()
    if not raw:
        await message.answer(
            "Файл пустой или недоступен. Пришлите фото чека или опишите трату текстом."
        )
        return

    extraction = await llm_client.extract_transactions_from_image(
        system_prompt,
        raw,
        mime,
        caption_or_hint=caption,
    )

    fb_date = _fallback_date_from_message(message)
    rows = records_from_extracted(extraction.transactions, fb_date, default_currency)
    transaction_store.add_many(chat_id, rows)

    reply = (extraction.reply_to_user or "").strip()
    if not reply:
        if rows:
            n = len(rows)
            reply = f"Записано операций: {n}. Спрашивайте /balance для сводки."
        else:
            reply = (
                "Не удалось выделить суммы на изображении. Попробуйте другой ракурс "
                "или опишите трату текстом."
            )

    user_line = "[Фото чека]" + (f": {caption}" if caption else "")
    conversation_store.add_exchange(chat_id, user_line, reply)
    parts = _split_text_for_telegram(reply)
    await message.answer(parts[0])
    for chunk in parts[1:]:
        await message.answer(chunk)
