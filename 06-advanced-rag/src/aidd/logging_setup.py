import logging
import sys
from typing import Final

_DEFAULT: Final[str] = "INFO"
_KNOWN = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def setup_logging(level_name: str) -> None:
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
