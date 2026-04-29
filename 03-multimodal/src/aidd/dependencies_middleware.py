from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from aidd.conversation_store import ConversationStore
from aidd.llm_client import LlmClient
from aidd.transaction_store import TransactionStore


class DependenciesMiddleware(BaseMiddleware):
    def __init__(
        self,
        conversation_store: ConversationStore,
        transaction_store: TransactionStore,
        llm_client: LlmClient,
        system_prompt: str,
        default_currency: str,
    ) -> None:
        super().__init__()
        self._conversation_store = conversation_store
        self._transaction_store = transaction_store
        self._llm_client = llm_client
        self._system_prompt = system_prompt
        self._default_currency = default_currency

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["conversation_store"] = self._conversation_store
        data["transaction_store"] = self._transaction_store
        data["llm_client"] = self._llm_client
        data["system_prompt"] = self._system_prompt
        data["default_currency"] = self._default_currency
        return await handler(event, data)
