"""Лимит частоты входящих текстовых сообщений Telegram по chat_id (скользящее окно — vision §12)."""

from __future__ import annotations

from aidd.config import AppConfig
from aidd.sliding_window_chat_limiter import SlidingWindowChatLimiter


class TelegramTextRateLimiter:
    """In-memory счётчик: не более ``max_messages`` событий за ``window_seconds`` на один ``chat_id``."""

    __slots__ = ("enabled", "max_messages", "window_seconds", "_limiter")

    def __init__(
        self,
        *,
        enabled: bool,
        window_seconds: float,
        max_messages: int,
    ) -> None:
        self.window_seconds = float(window_seconds)
        self.max_messages = int(max_messages)
        self.enabled = bool(
            enabled
            and self.window_seconds > 0.0
            and self.max_messages >= 1
        )
        self._limiter: SlidingWindowChatLimiter | None = None
        if self.enabled:
            self._limiter = SlidingWindowChatLimiter(
                window_seconds=self.window_seconds,
                max_events=self.max_messages,
            )

    @classmethod
    def from_app_config(cls, cfg: AppConfig) -> TelegramTextRateLimiter:
        return cls(
            enabled=cfg.telegram_text_rate_limit_enabled,
            window_seconds=cfg.telegram_text_rate_limit_window_seconds,
            max_messages=cfg.telegram_text_rate_limit_max_messages,
        )

    async def allow_text_message(self, chat_id: int) -> bool:
        """``True`` — сообщение можно обрабатывать (слот записан); ``False`` — превышен лимит."""
        if not self.enabled or self._limiter is None:
            return True
        return await self._limiter.try_acquire(chat_id)

    def explain_for_logs(self) -> str:
        if not self.enabled:
            return "off"
        return f"max={self.max_messages}/{self.window_seconds:g}s"
