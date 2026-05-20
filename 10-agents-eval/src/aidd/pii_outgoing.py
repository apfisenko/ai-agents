"""Маскирование PAN в текстах перед отправкой в Telegram (docs/vision.md п.12)."""

from __future__ import annotations

import re

# 16–19 цифр подряд, между цифрами — опционально пробелы/тире/thin space (vision §12).
_PAN_CHUNK_RE = re.compile(r"(?<!\d)(?:\d[ \-\t\u202f]*){16,19}(?!\d)")


def _mask_one_match(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    n = len(digits)
    return "*" * (n - 4) + digits[-4:] if n >= 16 else raw


def mask_pan_sequences(text: str) -> str:
    """Заменяет блоки PAN (16–19 цифр, см. vision) на «звёздочки + последние 4 цифры»."""
    if not text:
        return text

    def _sub(m: re.Match[str]) -> str:
        return _mask_one_match(m.group(0))

    return _PAN_CHUNK_RE.sub(_sub, text)


def maybe_mask_outgoing_pan(text: str, *, enabled: bool) -> str:
    """Без включённого флага возвращает исходный текст без копирования лишней логики."""
    return mask_pan_sequences(text) if (enabled and text) else text
