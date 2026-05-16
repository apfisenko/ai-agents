"""Команда /evaluate_dataset — прогон RAGAS + LangSmith feedback."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.bank_agent import BankAgentRunner
from aidd.config import AppConfig
from aidd.evaluation import EvaluationError, evaluate_dataset, format_summary_for_telegram

logger = logging.getLogger(__name__)

router = Router()

_TELEGRAM_CHUNK = 4096


def _split_telegram(text: str) -> list[str]:
    if len(text) <= _TELEGRAM_CHUNK:
        return [text]
    return [text[i : i + _TELEGRAM_CHUNK] for i in range(0, len(text), _TELEGRAM_CHUNK)]


@router.message(Command("evaluate_dataset"))
async def cmd_evaluate_dataset(
    message: Message,
    bank_runner: BankAgentRunner,
    app_config: AppConfig,
) -> None:
    await message.answer("Запускаю оценку на датасете LangSmith (RAGAS). Это может занять несколько минут…")
    try:
        summary = await evaluate_dataset(bank_runner, app_config)
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
