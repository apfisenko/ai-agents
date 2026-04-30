from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Tuple

REQUIRED: Final[Tuple[str, ...]] = (
    "TELEGRAM_BOT_TOKEN",
    "OPENROUTER_API_KEY",
    "LLM_MODEL",
    "OPENROUTER_BASE_URL",
    "SYSTEM_PROMPT_PATH",
    "LLM_MAX_COMPLETION_TOKENS",
)


def _parse_llm_http_timeout_seconds(raw: str) -> float:
    """Таймаут HTTP к LLM (сек.), только если переменная задана явно; диапазон 30–600."""
    s = raw.strip()
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        raise ValueError(
            f"LLM_HTTP_TIMEOUT_SECONDS must be a number (seconds), got: {raw!r}"
        ) from None
    if v < 30.0 or v > 600.0:
        raise ValueError(
            "LLM_HTTP_TIMEOUT_SECONDS must be between 30 and 600 "
            f"(got {v})"
        )
    return v


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


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    openrouter_api_key: str
    llm_model: str
    llm_audio_model: str
    llm_vision_model: str
    openrouter_base_url: str
    system_prompt_path: Path
    system_prompt_text: str
    log_level: str
    llm_max_completion_tokens: int
    llm_audio_max_completion_tokens: int
    llm_vision_max_completion_tokens: int
    llm_http_timeout_seconds: float | None
    default_currency: str

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
        raw_http = (os.environ.get("LLM_HTTP_TIMEOUT_SECONDS") or "").strip()
        llm_http_timeout = (
            None if not raw_http else _parse_llm_http_timeout_seconds(raw_http)
        )
        raw_currency = (os.environ.get("DEFAULT_CURRENCY") or "RUB").strip()
        default_currency = raw_currency.upper() if raw_currency else "RUB"
        raw_am = (os.environ.get("LLM_AUDIO_MODEL") or "").strip()
        llm_audio_model = raw_am or os.environ["LLM_MODEL"].strip()
        raw_vm = (os.environ.get("LLM_VISION_MODEL") or "").strip()
        llm_vision_model = raw_vm or os.environ["LLM_MODEL"].strip()
        raw_am_tok = (os.environ.get("LLM_AUDIO_MAX_COMPLETION_TOKENS") or "").strip()
        if raw_am_tok:
            llm_audio_max = _parse_llm_max_completion_tokens(raw_am_tok)
        else:
            llm_audio_max = min(8192, max(llm_max, 2048))
        raw_vm_tok = (os.environ.get("LLM_VISION_MAX_COMPLETION_TOKENS") or "").strip()
        if raw_vm_tok:
            llm_vision_max = _parse_llm_max_completion_tokens(raw_vm_tok)
        else:
            # VLM/reasoning часто исчерпывает лимит до появления JSON в content; не ниже 2048 при базовых 1024.
            llm_vision_max = min(8192, max(llm_max, 2048))
        return AppConfig(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"].strip(),
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"].strip(),
            llm_model=os.environ["LLM_MODEL"].strip(),
            llm_audio_model=llm_audio_model,
            llm_vision_model=llm_vision_model,
            openrouter_base_url=os.environ["OPENROUTER_BASE_URL"].strip().rstrip("/"),
            system_prompt_path=sp.resolve(),
            system_prompt_text=system_prompt_text,
            log_level=log_level,
            llm_max_completion_tokens=llm_max,
            llm_audio_max_completion_tokens=llm_audio_max,
            llm_vision_max_completion_tokens=llm_vision_max,
            llm_http_timeout_seconds=llm_http_timeout,
            default_currency=default_currency,
        )
