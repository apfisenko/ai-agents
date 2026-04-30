"""Голосовые сообщения Telegram → аудио в LLM (input_audio) → TransactionStore."""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.types import Message

from aidd.conversation_store import ConversationStore
from aidd.handlers.plain_text import (
    _LLM_UNAVAILABLE,
    _fallback_date_from_message,
    _split_text_for_telegram,
    _typing_while_waiting,
)
from aidd.llm_client import (
    LlmAudioPaymentRequiredError,
    LlmClient,
    LlmInvocationError,
)
from aidd.transaction_store import TransactionStore, records_from_extracted

logger = logging.getLogger(__name__)

router = Router()

_TELEGRAM_VOICE_DOWNLOAD_TIMEOUT = 120

_GENERIC_FAIL = (
    "Не удалось обработать голосовое сообщение. Опишите трату текстом или попробуйте позже."
)

_PAYMENT_REQUIRED_FOR_AUDIO = (
    "Не удалось обработать голос: провайдер (например OpenRouter) допускает запросы с аудио только "
    "при достаточном балансе (часто минимум около $0.50 на счёте). Обычные текст и фото чеков "
    "работают без этого. Пополните счёт или опишите трату текстом."
)


@router.message(F.voice)
async def voice_expense(
    message: Message,
    conversation_store: ConversationStore,
    transaction_store: TransactionStore,
    llm_client: LlmClient,
    system_prompt: str,
    default_currency: str,
) -> None:
    chat_id = message.chat.id
    typing_task = asyncio.create_task(_typing_while_waiting(message.bot, chat_id))
    try:
        await _process_voice_message(
            message,
            conversation_store,
            transaction_store,
            llm_client,
            system_prompt,
            default_currency,
        )
    except LlmAudioPaymentRequiredError:
        await message.answer(_PAYMENT_REQUIRED_FOR_AUDIO)
    except LlmInvocationError:
        await message.answer(_LLM_UNAVAILABLE)
    except Exception:
        logger.exception("Voice handler failed")
        try:
            await message.answer(_GENERIC_FAIL)
        except Exception:
            logger.warning("Could not send voice error reply to chat")
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


async def _process_voice_message(
    message: Message,
    conversation_store: ConversationStore,
    transaction_store: TransactionStore,
    llm_client: LlmClient,
    system_prompt: str,
    default_currency: str,
) -> None:
    chat_id = message.chat.id
    buf = BytesIO()
    voice = message.voice
    assert voice is not None
    mime = (voice.mime_type or "audio/ogg").strip()
    caption = (message.caption or "").strip()

    try:
        await message.bot.download(
            file=voice,
            destination=buf,
            timeout=_TELEGRAM_VOICE_DOWNLOAD_TIMEOUT,
        )
    except Exception as e:
        logger.warning("Telegram voice download failed: %s", type(e).__name__)
        await message.answer(
            "Не удалось загрузить голосовое сообщение. Отправьте его ещё раз."
        )
        return

    raw = buf.getvalue()
    if not raw:
        await message.answer(
            "Аудиофайл пустой или недоступен. Запишите сообщение ещё раз или напишите текстом."
        )
        return

    history = conversation_store.get_messages(chat_id)
    extraction = await llm_client.extract_transactions_from_audio(
        system_prompt,
        history,
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
                "Из голоса не удалось уверенно восстановить сумму: произнесите с цифрами "
                "(например «три ноль ноль рублей на продукты») или отправьте текстом. "
                "Длинную сумму только словами не все локальные модели по аудио воспринимают надёжно."
            )

    user_line = "[Голосовое сообщение]" + (f": {caption}" if caption else "")
    conversation_store.add_exchange(chat_id, user_line, reply)
    parts = _split_text_for_telegram(reply)
    await message.answer(parts[0])
    for chunk in parts[1:]:
        await message.answer(chunk)
