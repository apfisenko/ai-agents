"""Лимит числа обращений к графу агента (``ainvoke_turn``) на chat_id за скользящее окно — vision §12."""

from __future__ import annotations

from aidd.config import AppConfig
from aidd.sliding_window_chat_limiter import SlidingWindowChatLimiter

# Текст для пользователя при срабатывании лимита (не путать с FALLBACK_ASSISTANT_REPLY при пустом ответе LLM).
AGENT_INVOCATION_LIMIT_USER_REPLY = (
    "Превышено допустимое число обращений к ассистенту за короткое время. "
    "Разбейте запрос на части или обратитесь позже."
)


class AgentInvocationRateLimiter:
    """Один вызов ``ainvoke_turn`` = одно событие в окне ``WINDOW_AGENT_SECONDS``."""

    __slots__ = ("enabled", "max_invocations_per_window", "window_seconds", "_limiter")

    def __init__(
        self,
        *,
        enabled: bool,
        window_seconds: float,
        max_invocations_per_window: int,
    ) -> None:
        self.window_seconds = float(window_seconds)
        self.max_invocations_per_window = int(max_invocations_per_window)
        self.enabled = bool(
            enabled
            and self.window_seconds > 0.0
            and self.max_invocations_per_window >= 1
        )
        self._limiter: SlidingWindowChatLimiter | None = None
        if self.enabled:
            self._limiter = SlidingWindowChatLimiter(
                window_seconds=self.window_seconds,
                max_events=self.max_invocations_per_window,
            )

    @classmethod
    def from_app_config(cls, cfg: AppConfig) -> AgentInvocationRateLimiter:
        return cls(
            enabled=cfg.agent_invocations_rate_limit_enabled,
            window_seconds=cfg.window_agent_seconds,
            max_invocations_per_window=cfg.max_agent_invocations_per_window,
        )

    async def allow_agent_turn(self, chat_id: int) -> bool:
        """``True`` — можно вызывать ``ainvoke_turn`` (слот записан); ``False`` — лимит."""
        if not self.enabled or self._limiter is None:
            return True
        return await self._limiter.try_acquire(chat_id)

    def explain_for_logs(self) -> str:
        if not self.enabled:
            return "off"
        return f"max={self.max_invocations_per_window}/{self.window_seconds:g}s"
