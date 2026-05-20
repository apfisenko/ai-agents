"""Команда /mcp_status — проверка доступности MCP по URL из конфигурации."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aidd.config import AppConfig
from aidd.mcp_health import probe_mcp_bank

logger = logging.getLogger(__name__)

router = Router()

_TELEGRAM_ERR_MAX = 3500


@router.message(Command("mcp_status"))
async def cmd_mcp_status(message: Message, app_config: AppConfig) -> None:
    if not app_config.mcp_bank_enabled:
        await message.answer(
            "MCP в настройках отключён (`MCP_BANK_ENABLED=false`). "
            "Включите и перезапустите бота, чтобы подтягивать инструменты с сервера."
        )
        return

    url = app_config.mcp_bank_streamable_http_url
    probe = await probe_mcp_bank(url)
    if probe.ok:
        tools_line = ", ".join(probe.tool_names) if probe.tool_names else "(нет имён)"
        text = (
            "MCP доступен.\n"
            f"URL: `{url}`\n"
            f"Инструментов: {probe.tool_count}\n"
            f"{tools_line}"
        )
    else:
        err = probe.error or "неизвестная ошибка"
        if len(err) > _TELEGRAM_ERR_MAX:
            err = err[: _TELEGRAM_ERR_MAX - 3] + "..."
        text = (
            "MCP сейчас недоступен (бот при старте мог продолжить без MCP-инструментов).\n"
            f"URL: `{url}`\n"
            f"Ошибка: {err}"
        )
    await message.answer(text)
