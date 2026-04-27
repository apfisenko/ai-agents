import logging

from aiogram import Bot, Dispatcher

from aidd.config import AppConfig
from aidd.handlers import get_main_router

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, config: AppConfig) -> None:
        self._bot = Bot(token=config.telegram_bot_token)
        self._dp = Dispatcher()
        self._dp.include_router(get_main_router())

    async def run_polling(self) -> None:
        logger.info("Long polling started")
        try:
            await self._dp.start_polling(self._bot)
        finally:
            await self._bot.session.close()
