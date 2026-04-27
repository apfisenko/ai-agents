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
)


@dataclass(frozen=True)
class AppConfig:
    telegram_bot_token: str
    openrouter_api_key: str
    llm_model: str
    openrouter_base_url: str
    system_prompt_path: Path
    system_prompt_text: str
    log_level: str

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
        return AppConfig(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"].strip(),
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"].strip(),
            llm_model=os.environ["LLM_MODEL"].strip(),
            openrouter_base_url=os.environ["OPENROUTER_BASE_URL"].strip().rstrip("/"),
            system_prompt_path=sp.resolve(),
            system_prompt_text=system_prompt_text,
            log_level=log_level,
        )
