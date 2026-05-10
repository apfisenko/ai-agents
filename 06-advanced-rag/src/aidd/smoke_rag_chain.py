"""Регрессия ит.15 (KISS): индекс + один вызов RAG-цепочки как в Telegram (режим из .env).

Проверка retrieval-режима: задайте RAG_RETRIEVAL_MODE=semantic|hybrid|hybrid_rerank и при необходимости
повторите запуск. Нужны полные переменные из REQUIRED (AppConfig.from_env).

Запуск: `make smoke-rag-chain` или `uv run python -m aidd.smoke_rag_chain`.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from aidd.config import AppConfig
from aidd.rag_chain import RagChainRunner, format_sources_for_user
from aidd.vector_index import VectorIndexState


async def _run_once() -> None:
    config = AppConfig.from_env()
    logging.basicConfig(level=config.log_level)
    vi = VectorIndexState()
    vi.rebuild_from_config(config)
    runner = RagChainRunner(config, vi)
    res = await runner.ainvoke(
        [HumanMessage(content="Кратко: что относится к вкладам в справочнике?")]
    )
    print(f"answer_len={len(res.text)} docs={len(res.documents)}")
    if config.show_sources and res.documents:
        src = format_sources_for_user(res.documents)
        print(f"sources_preview={src[:200]}..." if len(src) > 200 else f"sources={src}")


def main() -> None:
    load_dotenv()
    try:
        asyncio.run(_run_once())
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    except Exception:
        logging.exception("smoke_rag_chain failed")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
