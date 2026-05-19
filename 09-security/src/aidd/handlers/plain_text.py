import asyncio
import logging

from aiogram import F, Router
from aiogram.types import Message

from aidd.agent_invocation_rate_limit import (
    AGENT_INVOCATION_LIMIT_USER_REPLY,
    AgentInvocationRateLimiter,
)
from aidd.bank_agent import BankAgentRunner
from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.handlers.hitl_callback import (
    build_hitl_resume_command,
    hitl_open_credit_card_keyboard,
)
from aidd.handlers.telegram_bank_response import (
    send_bank_turn_result_followup,
    typing_while_waiting,
)
from aidd.llm_client import (
    LlmInsufficientCreditsError,
    LlmInvocationError,
    TELEGRAM_REPLY_INSUFFICIENT_CREDITS,
)
from aidd.pii_outgoing import maybe_mask_outgoing_pan
from aidd.telegram_text_rate_limit import TelegramTextRateLimiter

logger = logging.getLogger(__name__)

router = Router()

_LLM_UNAVAILABLE = "Сервис временно недоступен. Попробуйте позже."
_RATE_LIMIT_USER_HINT = (
    "Слишком много сообщений за короткое время. Подождите немного и отправьте запрос снова."
)
_HITL_APPROVE_TOKENS = frozenset(
    {"да", "подтверждаю", "yes", "y", "ок", "ok", "okay", "approve"}
)
_HITL_REJECT_TOKENS = frozenset({"нет", "отмена", "no", "n", "reject", "отклонить"})


def _parse_hitl_text_reply(text: str) -> bool | None:
    """True — approve, False — reject, None — не распознано (ожидаются короткие ответы)."""
    t = (text or "").strip().lower()
    if t in _HITL_APPROVE_TOKENS:
        return True
    if t in _HITL_REJECT_TOKENS:
        return False
    return None


@router.message(F.text)
async def plain_text(
    message: Message,
    conversation_store: ConversationStore,
    bank_runner: BankAgentRunner,
    app_config: AppConfig,
    telegram_text_rate_limiter: TelegramTextRateLimiter,
    agent_invocation_rate_limiter: AgentInvocationRateLimiter,
) -> None:
    chat_id = message.chat.id
    text = message.text or ""
    if not await telegram_text_rate_limiter.allow_text_message(chat_id):
        logger.warning("plain_text: rate limit exceeded chat_id=%s user_len=%s", chat_id, len(text))
        await message.answer(_RATE_LIMIT_USER_HINT)
        return
    logger.info("plain_text: chat_id=%s user_len=%s", chat_id, len(text))
    typing_task = asyncio.create_task(typing_while_waiting(message.bot, chat_id))
    try:
        try:
            if bank_runner.hitl_is_waiting(chat_id):
                decision = _parse_hitl_text_reply(text)
                if decision is None:
                    await message.answer(
                        "Сначала подтвердите или отмените операцию кнопками Accept / "
                        "Reject или коротко: «ДА» / «НЕТ»."
                    )
                    return
                if not await agent_invocation_rate_limiter.allow_agent_turn(chat_id):
                    logger.warning(
                        "plain_text: agent invocation rate limit exceeded chat_id=%s user_len=%s",
                        chat_id,
                        len(text),
                    )
                    await message.answer(AGENT_INVOCATION_LIMIT_USER_REPLY)
                    return
                rag_result = await bank_runner.ainvoke_turn(
                    chat_id=chat_id,
                    resume_command=build_hitl_resume_command(decision),
                )
            else:
                if not await agent_invocation_rate_limiter.allow_agent_turn(chat_id):
                    logger.warning(
                        "plain_text: agent invocation rate limit exceeded chat_id=%s user_len=%s",
                        chat_id,
                        len(text),
                    )
                    await message.answer(AGENT_INVOCATION_LIMIT_USER_REPLY)
                    return
                rag_result = await bank_runner.ainvoke_turn(chat_id=chat_id, user_text=text)
                if rag_result.hitl_pending:
                    prompt = maybe_mask_outgoing_pan(
                        rag_result.hitl_user_prompt,
                        enabled=app_config.mask_pan_outgoing,
                    )
                    await message.answer(
                        prompt,
                        reply_markup=hitl_open_credit_card_keyboard(),
                    )
                    return
        except LlmInsufficientCreditsError:
            await message.answer(TELEGRAM_REPLY_INSUFFICIENT_CREDITS)
            return
        except LlmInvocationError:
            await message.answer(_LLM_UNAVAILABLE)
            return
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("typing task finished with error after cancel", exc_info=True)

    logger.info("plain_text: LLM готов, chat_id=%s reply_len=%s", chat_id, len(rag_result.text))
    await send_bank_turn_result_followup(
        message,
        rag_result,
        conversation_store=conversation_store,
        app_config=app_config,
    )
