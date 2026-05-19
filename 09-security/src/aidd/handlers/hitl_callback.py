"""Inline HITL: Accept / Reject для подтверждения операции перед вызовом open_credit_card."""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from langgraph.types import Command

from aidd.bank_agent import BankAgentRunner
from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.handlers.telegram_bank_response import (
    send_bank_turn_result_followup,
    typing_while_waiting,
)
from aidd.pii_outgoing import maybe_mask_outgoing_pan
from aidd.llm_client import (
    LlmInsufficientCreditsError,
    LlmInvocationError,
    TELEGRAM_REPLY_INSUFFICIENT_CREDITS,
)

logger = logging.getLogger(__name__)

router = Router()

_HITL_CB_APPROVE = "hitl_oc:approve"
_HITL_CB_REJECT = "hitl_oc:reject"

_LLM_UNAVAILABLE = "Сервис временно недоступен. Попробуйте позже."


def hitl_open_credit_card_keyboard() -> InlineKeyboardMarkup:
    """Inline-кнопки подтверждения операции открытия карты (vision §8)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Accept", callback_data=_HITL_CB_APPROVE),
                InlineKeyboardButton(text="Reject", callback_data=_HITL_CB_REJECT),
            ]
        ]
    )


def build_hitl_resume_command(approve: bool) -> Command:
    """Формирует Command для продолжения графа после решения пользователя."""
    if approve:
        return Command(resume={"decisions": [{"type": "approve"}]})
    return Command(
        resume={
            "decisions": [
                {
                    "type": "reject",
                    "message": "Пользователь отклонил операцию открытия кредитной карты.",
                }
            ]
        }
    )


@router.callback_query(F.data.in_({_HITL_CB_APPROVE, _HITL_CB_REJECT}))
async def hitl_open_credit_card_callback(
    query: CallbackQuery,
    conversation_store: ConversationStore,
    bank_runner: BankAgentRunner,
    app_config: AppConfig,
) -> None:
    if query.message is None:
        await query.answer()
        return

    chat_id = query.message.chat.id
    user_id = query.from_user.id if query.from_user else 0

    if query.message.chat.type == ChatType.PRIVATE and chat_id != user_id:
        await query.answer("Подтвердить может только владелец чата.", show_alert=True)
        return

    approve = query.data == _HITL_CB_APPROVE

    if not bank_runner.hitl_is_waiting(chat_id):
        await query.answer("Решение уже учтено.")
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logger.debug("edit_reply_markup (idempotent) failed", exc_info=True)
        return

    await query.answer()

    typing_task = asyncio.create_task(typing_while_waiting(query.bot, chat_id))
    try:
        try:
            rag_result = await bank_runner.ainvoke_turn(
                chat_id=chat_id,
                resume_command=build_hitl_resume_command(approve),
            )
        except LlmInsufficientCreditsError:
            await query.message.answer(TELEGRAM_REPLY_INSUFFICIENT_CREDITS)
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                logger.debug("edit_reply_markup after credits error failed", exc_info=True)
            return
        except LlmInvocationError:
            await query.message.answer(_LLM_UNAVAILABLE)
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                logger.debug("edit_reply_markup after LLM error failed", exc_info=True)
            return

        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logger.warning("Не удалось снять inline-клавиатуру после HITL", exc_info=True)

        if rag_result.hitl_pending:
            prompt = maybe_mask_outgoing_pan(
                rag_result.hitl_user_prompt,
                enabled=app_config.mask_pan_outgoing,
            )
            await query.message.answer(
                prompt,
                reply_markup=hitl_open_credit_card_keyboard(),
            )
            return

        await send_bank_turn_result_followup(
            query.message,
            rag_result,
            conversation_store=conversation_store,
            app_config=app_config,
        )
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("typing task finished with error after cancel", exc_info=True)
