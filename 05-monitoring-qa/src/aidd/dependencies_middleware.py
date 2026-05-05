from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from aidd.config import AppConfig
from aidd.conversation_store import ConversationStore
from aidd.rag_chain import RagChainRunner
from aidd.vector_index import VectorIndexState


class DependenciesMiddleware(BaseMiddleware):
    def __init__(
        self,
        conversation_store: ConversationStore,
        rag_runner: RagChainRunner,
        app_config: AppConfig,
        vector_index: VectorIndexState,
    ) -> None:
        super().__init__()
        self._conversation_store = conversation_store
        self._rag_runner = rag_runner
        self._app_config = app_config
        self._vector_index = vector_index

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["conversation_store"] = self._conversation_store
        data["rag_runner"] = self._rag_runner
        data["app_config"] = self._app_config
        data["vector_index"] = self._vector_index
        return await handler(event, data)
