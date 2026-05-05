"""Проверка итерации 5: построить индекс и выполнить similarity search."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import dotenv

from aidd.indexing import DEFAULT_EMBEDDING_MODEL, build_vector_store, default_data_dir


def main() -> None:
    dotenv.load_dotenv(Path.cwd() / ".env", override=False)
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").strip().upper())

    key = (os.environ.get("OPEN_API_KEY") or "").strip()
    base = (os.environ.get("OPEN_BASE_URL") or "").strip().rstrip("/")
    embedding_model = (
        os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
    ).strip()

    if not key or not base:
        print(
            "Задайте OPEN_API_KEY и OPEN_BASE_URL (см. .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)

    store, n_chunks = build_vector_store(
        data_dir=default_data_dir(),
        open_api_key=key,
        open_base_url=base,
        embedding_model=embedding_model,
    )
    print(f"chunks: {n_chunks}")

    query = "как заказать карту сбербанк"
    hits = store.similarity_search(query, k=2)
    print(f"similarity_search({query!r}), k=2:")
    for i, doc in enumerate(hits, start=1):
        preview = doc.page_content.replace("\n", " ")[:400]
        print(f"  [{i}] {preview}...")


if __name__ == "__main__":
    main()
