"""Общая реализация скользящего окна по chat_id для rate limiting (in-memory, async lock)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque


class SlidingWindowChatLimiter:
    """Не более ``max_events`` событий за ``window_seconds`` на один ``chat_id``."""

    __slots__ = ("max_events", "window_seconds", "_hits", "_lock")

    def __init__(self, *, window_seconds: float, max_events: int) -> None:
        self.window_seconds = float(window_seconds)
        self.max_events = int(max_events)
        self._lock = asyncio.Lock()
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    async def try_acquire(self, chat_id: int) -> bool:
        """Записать событие и вернуть ``True``; при переполнении окна — ``False`` (без записи)."""
        now = time.monotonic()
        cid = int(chat_id)
        async with self._lock:
            dq = self._hits[cid]
            cutoff = now - self.window_seconds
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max_events:
                return False
            dq.append(now)
            return True
