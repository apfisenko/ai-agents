"""Проверка доступности MCP-сервера mcp-bank-agent (streamable HTTP, get_tools)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _format_probe_error(exc: BaseException) -> str:
    """Читаемое сообщение (в т.ч. раскрытие ExceptionGroup от MCP-клиента)."""
    if isinstance(exc, BaseExceptionGroup):
        inner = [_format_probe_error(e) for e in list(exc.exceptions)[:3]]
        return f"{type(exc).__name__}: " + " | ".join(inner)
    return _format_error_one(exc)


def _format_error_one(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


@dataclass(frozen=True)
class McpBankProbeResult:
    ok: bool
    url: str
    tool_count: int
    tool_names: tuple[str, ...]
    error: str | None = None


async def probe_mcp_bank(url: str) -> McpBankProbeResult:
    """Полный handshake MCP: загрузка списка инструментов (как при старте бота)."""
    u = url.strip()
    if not u:
        return McpBankProbeResult(False, url, 0, (), "Пустой URL")

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(
            {
                "bank": {
                    "transport": "streamable_http",
                    "url": u,
                }
            }
        )
        tools = await client.get_tools()
        names = tuple(sorted(t.name for t in tools))
        return McpBankProbeResult(True, u, len(tools), names, None)
    except BaseException as exc:
        err = _format_probe_error(exc)
        logger.warning("MCP probe failed for %s: %s", u, err)
        return McpBankProbeResult(False, u, 0, (), err)


def default_mcp_url_from_env() -> str:
    return (os.environ.get("MCP_BANK_STREAMABLE_HTTP_URL") or "").strip() or (
        "http://127.0.0.1:8000/mcp"
    )


async def _run_check(url: str) -> int:
    res = await probe_mcp_bank(url)
    payload: dict = {"ok": res.ok, "url": res.url}
    if res.ok:
        payload["tool_count"] = res.tool_count
        payload["tools"] = list(res.tool_names)
    else:
        payload["error"] = res.error
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if res.ok else 1


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING"))
    load_dotenv()
    p = argparse.ArgumentParser(description="Проверка MCP mcp-bank-agent")
    p.add_argument(
        "command",
        choices=("check",),
        help="check — JSON в stdout и код выхода 0/1",
    )
    p.add_argument(
        "--url",
        default=None,
        help="Streamable HTTP endpoint (иначе MCP_BANK_STREAMABLE_HTTP_URL или 127.0.0.1:8000/mcp)",
    )
    args = p.parse_args()
    url = (args.url or "").strip() or default_mcp_url_from_env()
    code = asyncio.run(_run_check(url))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
