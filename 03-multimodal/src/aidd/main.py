from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

from dotenv import load_dotenv
from aiogram.exceptions import TelegramNetworkError

from aidd.config import AppConfig
from aidd.docker_context import is_docker_container
from aidd.logging_setup import setup_logging
from aidd.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _normalize_proxy_env_urls() -> None:
    """Схема в URL обязательна: 127.0.0.1:1301 → http://127.0.0.1:1301 (aiohttp/httpx)."""
    for key in _PROXY_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw or not str(raw).strip():
            continue
        val = str(raw).strip()
        if not _SCHEME_RE.match(val):
            os.environ[key] = f"http://{val}"


def _docker_use_http_proxy_in_container() -> bool:
    """True — оставить/переписать HTTP(S)_PROXY; False — сбросить (только прямой выход)."""
    v = (os.environ.get("AIDD_DOCKER_DIRECT_NETWORK") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return False
    if v in ("0", "false", "no", "off"):
        return True
    for key in _PROXY_ENV_KEYS:
        if (os.environ.get(key) or "").strip():
            return True
    return False


def _rewrite_loopback_proxy_for_docker() -> None:
    """В Docker: либо сброс прокси (прямой выход), либо подстановка хоста для локального HTTP-прокси."""
    if not is_docker_container():
        return
    if not _docker_use_http_proxy_in_container():
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        return
    win_host = (os.environ.get("AIDD_WINDOWS_PROXY_HOST") or "").strip()
    for key in _PROXY_ENV_KEYS:
        val = os.environ.get(key)
        if not val:
            continue
        new_val = (
            val.replace("127.0.0.1", "host.docker.internal")
            .replace("localhost", "host.docker.internal")
        )
        if win_host:
            new_val = new_val.replace("host.docker.internal", win_host)
        if new_val != val:
            os.environ[key] = new_val


def main() -> None:
    load_dotenv()
    _normalize_proxy_env_urls()
    _rewrite_loopback_proxy_for_docker()
    try:
        config = AppConfig.from_env()
    except ValueError as e:
        print(f"Config error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    setup_logging(config.log_level)
    logger.info("Configuration loaded, starting application")
    logger.info(
        "System prompt: %s (%d chars)",
        config.system_prompt_path,
        len(config.system_prompt_text),
    )
    logger.info(
        "LLM: текст=%s; фото чеков=%s",
        config.llm_model,
        config.llm_vision_model,
    )
    if is_docker_container() and (
        (os.environ.get("HTTPS_PROXY") or "").strip() or (os.environ.get("HTTP_PROXY") or "").strip()
    ):
        logger.info(
            "Docker + прокси: при ClientProxyConnectionError к IP хоста:порт см. ReadMe "
            "(Allow LAN в VPN или перенаправление netsh portproxy на Windows)."
        )
    try:
        exit_code = asyncio.run(_run(config))
    except KeyboardInterrupt:
        logger.info("Shutdown requested (KeyboardInterrupt)")
        return
    if exit_code:
        raise SystemExit(exit_code)


async def _run(config: AppConfig) -> int:
    app = TelegramBot(config)
    try:
        await app.run_polling()
        return 0
    except TelegramNetworkError as e:
        msg = (
            "Не удалось подключиться к Telegram API (сеть, firewall, прокси или блокировка). "
            "Проверьте доступ: например, Test-NetConnection api.telegram.org -Port 443. "
            "(TelegramNetworkError)"
        )
        detail = e.message or ""
        hint = ""
        if is_docker_container() and "timeout" in detail.lower():
            hint = (
                " Подсказка (Docker): из контейнера нет рабочего пути к api.telegram.org "
                "или прокси на хосте не отвечает — см. ReadMe (Request timeout, portproxy, mirrored WSL). "
                "Обход без Docker: .\\make.ps1 run (PowerShell) из корня проекта."
            )
        elif is_docker_container() and "ClientProxyConnectionError" in detail and "host.docker.internal" in detail:
            hint = (
                " Подсказка: при Docker через WSL, если порт 172.17.x (часто) — в .env задайте "
                "AIDD_WINDOWS_PROXY_HOST= из вывода: .\\make.ps1 docker-windows-host-ip, затем снова docker-up. "
                "См. ReadMe, раздел про ClientProxyConnectionError и 172.17.0.1."
            )
        logger.error("%s Детали: %s%s", msg, detail, hint)
        print(f"{msg}\nДетали: {detail}{hint}", file=sys.stderr)
        return 1
    finally:
        await app.close()
