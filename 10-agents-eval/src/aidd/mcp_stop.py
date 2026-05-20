"""Остановка процесса, слушающего порт MCP-сервера mcp-bank-agent (по умолчанию 8000)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def resolve_mcp_listen_port() -> int:
    raw = (os.environ.get("MCP_BANK_PORT") or "").strip()
    if raw.isdigit():
        p = int(raw)
        return max(1, min(p, 65535))
    url = (os.environ.get("MCP_BANK_STREAMABLE_HTTP_URL") or "").strip()
    if url:
        pr = urlparse(url)
        if pr.port is not None:
            return pr.port
    return 8000


def pids_listening_on_port(port: int) -> list[int]:
    if sys.platform == "win32":
        return _pids_listening_windows(port)
    return _pids_listening_unix(port)


def _pids_listening_windows(port: int) -> list[int]:
    r = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if r.returncode != 0:
        logger.warning("netstat -ano завершился с кодом %s", r.returncode)
        return []
    needle = f":{port}"
    pids: set[int] = set()
    for line in (r.stdout or "").splitlines():
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    return sorted(pids)


def _pids_listening_unix(port: int) -> list[int]:
    r = subprocess.run(
        ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        return []
    out: list[int] = []
    for tok in (r.stdout or "").strip().split():
        try:
            out.append(int(tok))
        except ValueError:
            continue
    return sorted(set(out))


def terminate_pids(pids: list[int], *, force: bool) -> tuple[list[int], list[str]]:
    """Завершает процессы. Windows: taskkill /F. Unix: SIGTERM или SIGKILL при force."""
    errors: list[str] = []
    killed: list[int] = []
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=True,
                )
            else:
                os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
                if not force:
                    time.sleep(0.15)
            killed.append(pid)
        except Exception as exc:
            errors.append(f"pid {pid}: {type(exc).__name__}: {exc}")
    return killed, errors


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    load_dotenv()
    p = argparse.ArgumentParser(description="Остановка mcp-bank-agent на listen-порту")
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help="Порт (иначе MCP_BANK_PORT или URL из MCP_BANK_STREAMABLE_HTTP_URL, иначе 8000)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Unix: SIGKILL. Windows: как обычно taskkill /F",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Результат в JSON на stdout",
    )
    args = p.parse_args()
    port = int(args.port) if args.port is not None else resolve_mcp_listen_port()
    pids = pids_listening_on_port(port)
    if not pids:
        msg = {"ok": True, "port": port, "stopped": [], "note": "нет LISTENING-процессов на порту"}
        if args.json:
            print(json.dumps(msg, ensure_ascii=False))
        else:
            print(f"Порт {port}: слушающих процессов не найдено (уже остановлено или другой порт).")
        raise SystemExit(0)

    logger.info("Останавливаю PID %s на порту %s", pids, port)
    win = sys.platform == "win32"
    killed, errors = terminate_pids(pids, force=args.force or win)
    ok = not errors
    payload = {
        "ok": ok,
        "port": port,
        "stopped": killed,
        "errors": errors or None,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if killed:
            print(f"Порт {port}: завершены процессы PID {killed}.")
        for e in errors:
            print(f"Ошибка: {e}", file=sys.stderr)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
