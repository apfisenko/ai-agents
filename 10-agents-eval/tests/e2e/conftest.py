"""Общие фикстуры e2e агента: полный AppConfig, индекс, MCP выключен для стабильного набора tools."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from aidd.bank_agent import BankAgentRunner, initialize_agent
from aidd.config import AppConfig
from aidd.indexed_retrieval import IndexedRetriever
from aidd.vector_index import VectorIndexState


def _require_e2e_env() -> None:
    """Без полного .env как у бота тесты не запускаем."""
    load_dotenv(override=False)
    if not (os.environ.get("OPEN_API_KEY") or "").strip():
        pytest.skip("Нужен OPEN_API_KEY в окружении (.env)")
    if not (os.environ.get("OPEN_BASE_URL") or "").strip():
        pytest.skip("Нужен OPEN_BASE_URL в окружении (.env)")


@pytest_asyncio.fixture
async def e2e_bank_runner(monkeypatch: pytest.MonkeyPatch) -> BankAgentRunner:
    _require_e2e_env()
    load_dotenv(override=False)
    monkeypatch.setenv("MCP_BANK_ENABLED", "false")
    # Не ходим в Hugging Face (эмбеддинги / cross-encoder): иначе e2e ломается при мёртвом HTTPS_PROXY.
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", "semantic")

    config = AppConfig.from_env()
    vi = VectorIndexState()
    vi.rebuild_from_config(config)
    indexed = IndexedRetriever(config, vi)
    return await initialize_agent(config, indexed)


def unique_thread_id(prefix: str = "e2e") -> str:
    return f"{prefix}-{uuid.uuid4()}"


def reference_must_call_tool(tool_name: str) -> list[AIMessage]:
    """Минимальная эталонная траектория: один вызов инструмента (режим superset + ignore args)."""
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": tool_name,
                    "args": {"query": "placeholder"},
                    "id": "e2e-ref-placeholder",
                    "type": "tool_call",
                }
            ],
        )
    ]
