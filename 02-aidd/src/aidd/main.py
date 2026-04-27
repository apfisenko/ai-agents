from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

from aidd.config import AppConfig
from aidd.logging_setup import setup_logging
from aidd.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    try:
        config = AppConfig.from_env()
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    setup_logging(config.log_level)
    logger.info("Configuration loaded, starting application")
    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:
        logger.info("Shutdown requested (KeyboardInterrupt)")


async def _run(config: AppConfig) -> None:
    app = TelegramBot(config)
    await app.run_polling()
