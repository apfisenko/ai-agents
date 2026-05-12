import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

from aidd.bank_agent import BankAgentRunner
from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.dependencies_middleware import DependenciesMiddleware
from aidd.handlers import get_main_router
from aidd.indexed_retrieval import IndexedRetriever
from aidd.rag_chain import RagChainRunner
from aidd.telegram_session import TrustEnvAiohttpSession
from aidd.vector_index import VectorIndexState
from langgraph.checkpoint.memory import InMemorySaver

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
        self._config = config
        self._conversation_store = ConversationStore()
        self._vector_index = VectorIndexState()
        self._indexed_retriever = IndexedRetriever(config, self._vector_index)
        self._agent_checkpointer = InMemorySaver()
        self._bank_runner = BankAgentRunner.build(
            config, self._indexed_retriever, checkpointer=self._agent_checkpointer
        )
        self._rag_runner = RagChainRunner(
            config,
            self._vector_index,
            indexed_retriever=self._indexed_retriever,
        )
        self._bot = Bot(
            token=config.telegram_bot_token,
            session=TrustEnvAiohttpSession(timeout=_telegram_http_timeout()),
        )
        self._dp = Dispatcher()
        self._dp.update.middleware(
            DependenciesMiddleware(
                self._conversation_store,
                self._rag_runner,
                self._bank_runner,
                config,
                self._vector_index,
            )
        )
        self._dp.include_router(get_main_router())

    @property
    def config(self) -> AppConfig:
        return self._config

    async def bootstrap_vector_index(self) -> None:
        """Полная переиндексация при старте (vision §7). Блокирующий вызов — в thread pool."""
        await asyncio.to_thread(self._vector_index.rebuild_from_config, self._config)
        logger.info("Vector index ready: %d chunks", self._vector_index.chunk_count)

    async def close(self) -> None:
        # Bot.session — aiogram AiohttpSession, не aiohttp.ClientSession; закрытие внутри session.close()
        await self._bot.session.close()

    async def run_polling(self) -> None:
        # Иначе getUpdates не получает апдейты (тишина в чате при long polling)
        await self._bot.delete_webhook(drop_pending_updates=False)
        logger.info("Webhook сброшен; long polling (getUpdates) активен")

        await self._dp.start_polling(self._bot)
