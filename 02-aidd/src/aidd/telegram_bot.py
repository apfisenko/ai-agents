import logging

from aiogram import Bot, Dispatcher

from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.dependencies_middleware import DependenciesMiddleware
from aidd.handlers import get_main_router
from aidd.llm_client import LlmClient
from aidd.telegram_session import TrustEnvAiohttpSession

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, config: AppConfig) -> None:
        self._conversation_store = ConversationStore()
        self._llm_client = LlmClient(
            api_key=config.openrouter_api_key,
            base_url=config.openrouter_base_url,
            model=config.llm_model,
        )
        self._bot = Bot(
            token=config.telegram_bot_token,
            session=TrustEnvAiohttpSession(),
        )
        self._dp = Dispatcher()
        self._dp.update.middleware(
            DependenciesMiddleware(
                self._conversation_store,
                self._llm_client,
                config.system_prompt_text,
            )
        )
        self._dp.include_router(get_main_router())

    async def close(self) -> None:
        # Bot.session — aiogram AiohttpSession, не aiohttp.ClientSession; закрытие внутри session.close()
        await self._bot.session.close()

    async def run_polling(self) -> None:
        # Иначе getUpdates не получает апдейты (тишина в чате при long polling)
        await self._bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook сброшен; long polling (getUpdates) активен")

        await self._dp.start_polling(self._bot)
