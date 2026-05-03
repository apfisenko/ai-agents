"""Состояние векторного индекса в памяти (InMemoryVectorStore)."""

from __future__ import annotations

import logging
from threading import Lock

from langchain_core.vectorstores import InMemoryVectorStore

from aidd.config import AppConfig
from aidd.indexing import build_vector_store, default_data_dir

logger = logging.getLogger(__name__)


class VectorIndexState:
    """Потокобезопасное хранилище ссылки на построенный индекс и числа чанков."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._store: InMemoryVectorStore | None = None
        self._chunk_count: int = 0

    def rebuild_from_config(self, config: AppConfig) -> None:
        """Полная переиндексация. При ошибке выбрасывает исключение (вызывающий решает UX)."""
        data_dir = default_data_dir()
        logger.info("Indexing from data dir %s", data_dir)
        store, n = build_vector_store(
            data_dir=data_dir,
            open_api_key=config.open_api_key,
            open_base_url=config.open_base_url,
            embedding_model=config.embedding_model,
        )
        with self._lock:
            self._store = store
            self._chunk_count = n
        logger.info("Index built: %d chunks", n)

    @property
    def chunk_count(self) -> int:
        with self._lock:
            return self._chunk_count

    def get_store(self) -> InMemoryVectorStore | None:
        with self._lock:
            return self._store
