import logging
import os

from aiogram import Bot, Dispatcher

from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.dependencies_middleware import DependenciesMiddleware
from aidd.handlers import get_main_router
from aidd.llm_client import LlmClient
from aidd.telegram_session import TrustEnvAiohttpSession
from aidd.transaction_store import TransactionStore

logger = logging.getLogger(__name__)


def _telegram_http_timeout() -> float:
    """Таймаут HTTP к Telegram (сек.); по умолчанию 60, как в aiogram. См. TELEGRAM_HTTP_TIMEOUT."""
    raw = (os.environ.get("TELEGRAM_HTTP_TIMEOUT") or "").strip()
    if not raw:
        return 60.0
    try:
        return max(10.0, min(float(raw), 600.0))
    except ValueError:
        return 60.0


class TelegramBot:
    def __init__(self, config: AppConfig) -> None:
        self._conversation_store = ConversationStore()
        self._transaction_store = TransactionStore()
        self._llm_client = LlmClient(
            api_key=config.openrouter_api_key,
            base_url=config.openrouter_base_url,
            model=config.llm_model,
            max_completion_tokens=config.llm_max_completion_tokens,
            vision_model=config.llm_vision_model,
            vision_max_completion_tokens=config.llm_vision_max_completion_tokens,
            http_timeout_seconds=config.llm_http_timeout_seconds,
        )
        self._bot = Bot(
            token=config.telegram_bot_token,
            session=TrustEnvAiohttpSession(timeout=_telegram_http_timeout()),
        )
        self._dp = Dispatcher()
        self._dp.update.middleware(
            DependenciesMiddleware(
                self._conversation_store,
                self._transaction_store,
                self._llm_client,
                config.system_prompt_text,
                config.default_currency,
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
