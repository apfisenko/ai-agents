"""Лимит частоты входящих текстовых сообщений Telegram по chat_id (скользящее окно — vision §12)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from aidd.config import AppConfig


class TelegramTextRateLimiter:
    """In-memory счётчик: не более ``max_messages`` событий за ``window_seconds`` на один ``chat_id``."""

    __slots__ = ("enabled", "max_messages", "window_seconds", "_hits", "_lock")

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
        self._lock = asyncio.Lock()
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    @classmethod
    def from_app_config(cls, cfg: AppConfig) -> TelegramTextRateLimiter:
        return cls(
            enabled=cfg.telegram_text_rate_limit_enabled,
            window_seconds=cfg.telegram_text_rate_limit_window_seconds,
            max_messages=cfg.telegram_text_rate_limit_max_messages,
        )

    async def allow_text_message(self, chat_id: int) -> bool:
        """``True`` — сообщение можно обрабатывать (слот записан); ``False`` — превышен лимит."""
        if not self.enabled:
            return True
        now = time.monotonic()
        cid = int(chat_id)
        async with self._lock:
            dq = self._hits[cid]
            cutoff = now - self.window_seconds
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max_messages:
                return False
            dq.append(now)
            return True

    def explain_for_logs(self) -> str:
        if not self.enabled:
            return "off"
        return f"max={self.max_messages}/{self.window_seconds:g}s"
