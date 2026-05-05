from __future__ import annotations

from openai import APIStatusError

# Единый текст для Telegram при отказе провайдера из‑за кредитов (OpenRouter 402 и аналоги).
TELEGRAM_REPLY_INSUFFICIENT_CREDITS = (
    "У провайдера моделей закончились кредиты (ошибка оплаты API). "
    "Пополните баланс или проверьте ключ в настройках OpenRouter — это отличается от обычной недоступности сервиса."
)


class LlmInvocationError(Exception):
    """Сбой вызова LLM; пользовательское сообщение формирует handler."""


class LlmInsufficientCreditsError(LlmInvocationError):
    """Провайдер вернул отказ из‑за отсутствия кредитов (например HTTP 402)."""


def is_insufficient_credits_error(exc: BaseException) -> bool:
    """Тот же признак, что и для LLM: эмбеддинги при индексации могут оборачивать APIStatusError."""
    if isinstance(exc, LlmInsufficientCreditsError):
        return True
    if isinstance(exc, APIStatusError) and getattr(exc, "status_code", None) == 402:
        return True
    msg = str(exc).lower()
    if "insufficient credits" in msg:
        return True
    if "402" in msg and "credit" in msg:
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_insufficient_credits_error(cause)
    ctx = getattr(exc, "__context__", None)
    if ctx is not None and ctx is not exc:
        return is_insufficient_credits_error(ctx)
    return False
