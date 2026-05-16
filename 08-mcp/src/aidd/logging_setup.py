import logging
import sys
from typing import Final, TextIO

_DEFAULT: Final[str] = "INFO"
_KNOWN = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _try_reconfigure_utf8(stream: TextIO) -> None:
    """Windows: консоль часто cp1251 — лог/трейс с Unicode (ответ LLM, U+202F и т.д.) даёт UnicodeEncodeError и роняет хендлер."""
    reconf = getattr(stream, "reconfigure", None)
    if callable(reconf):
        try:
            reconf(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            pass


def setup_logging(level_name: str) -> None:
    if sys.platform == "win32":
        _try_reconfigure_utf8(sys.stdout)
        _try_reconfigure_utf8(sys.stderr)
    raw = (level_name or _DEFAULT).strip().upper()
    if raw in _KNOWN:
        level: int = getattr(logging, raw)
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
