import asyncio
import logging
import os
from typing import Self

from aiogram import Bot, Dispatcher
from aiogram.types.error_event import ErrorEvent

from aidd.bank_agent import BankAgentRunner, initialize_agent
from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.dependencies_middleware import DependenciesMiddleware
from aidd.handlers import get_main_router
from aidd.indexed_retrieval import IndexedRetriever
from aidd.rag_chain import RagChainRunner
from aidd.telegram_session import TrustEnvAiohttpSession
from aidd.telegram_text_rate_limit import TelegramTextRateLimiter
from aidd.vector_index import VectorIndexState
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

_ERR_USER_HINT = (
    "Не удалось обработать запрос (внутренняя ошибка). Если после перезапуска не проходит — "
    "смотрите лог сервера и проверьте ключ/модель OpenRouter."
)


def _register_error_handler(dp: Dispatcher) -> None:
    """Чтобы при сбое в хендлере пользователь не оставался без ответа и ошибка была в логе."""

    @dp.error()
    async def _on_handler_error(event: ErrorEvent, bot: Bot) -> bool:  # noqa: ARG001
        logger.error(
            "Ошибка при обработке апдейта Telegram",
            exc_info=event.exception,
        )
        msg = event.update.message or event.update.edited_message
        if msg is not None:
            try:
                await msg.answer(_ERR_USER_HINT)
            except Exception:
                logger.warning("Не удалось отправить пользователю сообщение об ошибке", exc_info=True)
        return True


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
    """Telegram + RAG + банковский агент. Сборка с async-инициализацией MCP: ``await TelegramBot.create``."""

    def __init__(
        self,
        config: AppConfig,
        *,
        conversation_store: ConversationStore,
        vector_index: VectorIndexState,
        indexed_retriever: IndexedRetriever,
        agent_checkpointer: InMemorySaver,
        bank_runner: BankAgentRunner,
        rag_runner: RagChainRunner,
        bot: Bot,
        dp: Dispatcher,
    ) -> None:
        self._config = config
        self._conversation_store = conversation_store
        self._vector_index = vector_index
        self._indexed_retriever = indexed_retriever
        self._agent_checkpointer = agent_checkpointer
        self._bank_runner = bank_runner
        self._rag_runner = rag_runner
        self._bot = bot
        self._dp = dp

    @classmethod
    async def create(cls, config: AppConfig) -> Self:
        conversation_store = ConversationStore()
        vector_index = VectorIndexState()
        indexed_retriever = IndexedRetriever(config, vector_index)
        agent_checkpointer = InMemorySaver()
        bank_runner = await initialize_agent(
            config, indexed_retriever, checkpointer=agent_checkpointer
        )
        rag_runner = RagChainRunner(
            config,
            vector_index,
            indexed_retriever=indexed_retriever,
        )
        bot = Bot(
            token=config.telegram_bot_token,
            session=TrustEnvAiohttpSession(timeout=_telegram_http_timeout()),
        )
        text_limiter = TelegramTextRateLimiter.from_app_config(config)
        logger.info("Telegram text rate limit: %s", text_limiter.explain_for_logs())
        dp = Dispatcher()
        dp.update.middleware(
            DependenciesMiddleware(
                conversation_store,
                rag_runner,
                bank_runner,
                config,
                vector_index,
                text_limiter,
            )
        )
        dp.include_router(get_main_router())
        _register_error_handler(dp)
        return cls(
            config,
            conversation_store=conversation_store,
            vector_index=vector_index,
            indexed_retriever=indexed_retriever,
            agent_checkpointer=agent_checkpointer,
            bank_runner=bank_runner,
            rag_runner=rag_runner,
            bot=bot,
            dp=dp,
        )

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
