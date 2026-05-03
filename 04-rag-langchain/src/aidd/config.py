from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Tuple

from aidd.indexing import DEFAULT_EMBEDDING_MODEL

REQUIRED: Final[Tuple[str, ...]] = (
    "TELEGRAM_BOT_TOKEN",
    "OPEN_API_KEY",
    "LLM_MODEL",
    "OPEN_BASE_URL",
    "SYSTEM_PROMPT_PATH",
    "LLM_MAX_COMPLETION_TOKENS",
    "RETRIEVER_K",
)


def _parse_llm_max_completion_tokens(raw: str) -> int:
    s = raw.strip()
    try:
        v = int(s)
    except ValueError:
        raise ValueError(
            f"LLM_MAX_COMPLETION_TOKENS must be an integer between 64 and 8192, got: {raw!r}"
        ) from None
    if v < 64 or v > 8192:
        raise ValueError(
            "LLM_MAX_COMPLETION_TOKENS must be an integer between 64 and 8192 "
            f"(got {v})"
        )
    return v


def _parse_retriever_k(raw: str) -> int:
    s = raw.strip()
    try:
        v = int(s)
    except ValueError:
        raise ValueError(
            f"RETRIEVER_K must be an integer between 1 and 50, got: {raw!r}"
        ) from None
    if v < 1 or v > 50:
        raise ValueError(f"RETRIEVER_K must be between 1 and 50 (got {v})")
    return v


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    open_api_key: str
    llm_model: str  # ответ пользователю в RAG
    llm_query_transform_model: str  # преобразование запроса; по умолчанию = LLM_MODEL
    open_base_url: str
    system_prompt_path: Path
    system_prompt_text: str
    log_level: str
    llm_max_completion_tokens: int
    retriever_k: int
    embedding_model: str

    @staticmethod
    def from_env() -> "AppConfig":
        missing = [k for k in REQUIRED if not (os.environ.get(k) or "").strip()]
        if missing:
            raise ValueError(
                f"Missing or empty required environment variable(s): {', '.join(missing)}"
            )
        sp = Path(os.environ["SYSTEM_PROMPT_PATH"].strip()).expanduser()
        if not sp.is_file():
            raise ValueError(
                f"SYSTEM_PROMPT_PATH is not a path to a readable file: {sp} "
                f"(set an existing file; see .env.example)"
            )
        try:
            raw = sp.read_text(encoding="utf-8")
        except OSError as e:
            raise ValueError(f"Cannot read SYSTEM_PROMPT_PATH file: {sp}") from e
        # UTF-8 BOM в начале файла с Windows-редактора мешает первой строке
        if raw.startswith("\ufeff"):
            raw = raw[1:]
        system_prompt_text = raw.strip()
        log_level = (os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
        llm_max = _parse_llm_max_completion_tokens(
            os.environ["LLM_MAX_COMPLETION_TOKENS"]
        )
        retriever_k = _parse_retriever_k(os.environ["RETRIEVER_K"])
        embedding_raw = (os.environ.get("EMBEDDING_MODEL") or "").strip()
        embedding_model = embedding_raw or DEFAULT_EMBEDDING_MODEL
        llm_model = os.environ["LLM_MODEL"].strip()
        qt_raw = (os.environ.get("LLM_QUERY_TRANSFORM_MODEL") or "").strip()
        llm_query_transform_model = qt_raw or llm_model
        return AppConfig(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"].strip(),
            open_api_key=os.environ["OPEN_API_KEY"].strip(),
            llm_model=llm_model,
            llm_query_transform_model=llm_query_transform_model,
            open_base_url=os.environ["OPEN_BASE_URL"].strip().rstrip("/"),
            system_prompt_path=sp.resolve(),
            system_prompt_text=system_prompt_text,
            log_level=log_level,
            llm_max_completion_tokens=llm_max,
            retriever_k=retriever_k,
            embedding_model=embedding_model,
        )
