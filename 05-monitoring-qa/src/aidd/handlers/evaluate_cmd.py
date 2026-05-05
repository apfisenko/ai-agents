"""Команда /evaluate_dataset — прогон RAGAS + LangSmith feedback."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.evaluation import EvaluationError, format_summary_for_telegram, run_ragas_evaluation_with_feedback
from aidd.rag_chain import RagChainRunner

logger = logging.getLogger(__name__)

router = Router()

_TELEGRAM_CHUNK = 4096


def _split_telegram(text: str) -> list[str]:
    if len(text) <= _TELEGRAM_CHUNK:
        return [text]
    return [text[i : i + _TELEGRAM_CHUNK] for i in range(0, len(text), _TELEGRAM_CHUNK)]


@router.message(Command("evaluate_dataset"))
async def cmd_evaluate_dataset(message: Message, rag_runner: RagChainRunner) -> None:
    await message.answer("Запускаю оценку на датасете LangSmith (RAGAS). Это может занять несколько минут…")
    try:
        summary = await asyncio.to_thread(run_ragas_evaluation_with_feedback, rag_runner)
    except EvaluationError as e:
        logger.warning("Evaluate dataset: %s", e)
        await message.answer(str(e))
        return
    except Exception:
        logger.exception("Evaluate dataset failed")
        await message.answer(
            "Оценка не выполнена (внутренняя ошибка или сеть). См. логи сервера."
        )
        return

    text = format_summary_for_telegram(summary)
    parts = _split_telegram(text)
    await message.answer(parts[0])
    for chunk in parts[1:]:
        await message.answer(chunk)
