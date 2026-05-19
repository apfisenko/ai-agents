"""Поиск и остановка процессов «uv run python -m aidd» / «python -m aidd» (конфликт Telegram getUpdates)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import NamedTuple

from dotenv import load_dotenv

_AIDD_RUN = re.compile(r"-m\s+aidd(\s|$)")

_WINDOWS_VENV_NOTE = (
    "На Windows один запуск «python -m aidd» из .venv часто даёт 2 процесса ОС: лаунчер "
    "(.venv\\Scripts\\python.exe) и рабочий интерпретатор (каталог home из pyvenv.cfg). "
    "Это один экземпляр бота; смотрите «логических экземпляров»."
)


class ProcRow(NamedTuple):
    pid: int
    ppid: int | None
    cmd: str


def _is_bot_python_cmdline(name: str | None, cmd: str | None) -> bool:
    if not cmd or "-m aidd." in cmd:
        return False
    if not _AIDD_RUN.search(cmd):
        return False
    base = os.path.basename(name or "").lower()
    if sys.platform == "win32":
        return bool(re.fullmatch(r"python(w)?\.exe", base))
    return base.startswith("python")


def _logical_bot_rows(rows: list[ProcRow]) -> list[ProcRow]:
    """Исключает родителя, если в списке есть его потомок с той же командной строкой (лаунчер venv Windows)."""
    by_pid = {r.pid: r for r in rows}
    launcher_pids: set[int] = set()
    for r in rows:
        if r.ppid is None or r.ppid not in by_pid:
            continue
        parent = by_pid[r.ppid]
        if parent.cmd == r.cmd:
            launcher_pids.add(parent.pid)
    return [r for r in rows if r.pid not in launcher_pids]


def list_aidd_python_rows() -> list[ProcRow]:
    if sys.platform == "win32":
        return _list_windows()
    return _list_unix()


def _list_windows() -> list[ProcRow]:
    ps = r"""
$rows = Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and (
      $_.Name -match '^(python|pythonw)\.exe$'
    ) -and ($_.CommandLine -match '-m\s+aidd(\s|$)') -and ($_.CommandLine -notmatch '-m\s+aidd\.')
  }
foreach ($r in $rows) {
  "{0}`t{1}`t{2}" -f $r.ProcessId, $r.ParentProcessId, ($r.CommandLine -replace "`r`n|`n|`r", " ")
}
""".strip()
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if r.returncode != 0:
        return []
    out: list[ProcRow] = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line or line.count("\t") < 2:
            continue
        pid_s, ppid_s, cmd = line.split("\t", 2)
        try:
            pid = int(pid_s.strip())
            ppid = int(ppid_s.strip())
        except ValueError:
            continue
        out.append(ProcRow(pid, ppid, cmd.strip()))
    return sorted(set(out), key=lambda x: x.pid)


def _list_unix() -> list[ProcRow]:
    if sys.platform == "darwin":
        args = ["ps", "-ax", "-o", "pid=", "-o", "ppid=", "-o", "command="]
    else:
        args = ["ps", "-eo", "pid=", "-o", "ppid=", "-o", "args="]
    r = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if r.returncode != 0 or not (r.stdout or "").strip():
        return []
    rows: list[ProcRow] = []
    for raw in (r.stdout or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        cmd = parts[2]
        name = cmd.split(None, 1)[0] if cmd else ""
        base = os.path.basename(name).lower()
        if not _is_bot_python_cmdline(base, cmd):
            continue
        rows.append(ProcRow(pid, ppid, cmd))
    return sorted(set(rows), key=lambda x: x.pid)


def cmd_check(*, json_out: bool) -> int:
    rows = list_aidd_python_rows()
    logical = _logical_bot_rows(rows)
    conflict = len(logical) > 1 if rows else False
    if json_out:
        print(
            json.dumps(
                {
                    "os_process_count": len(rows),
                    "logical_bot_count": len(logical),
                    "conflict_risk": conflict,
                    "pids_all": [r.pid for r in rows],
                    "pids_logical": [r.pid for r in logical],
                    "processes": [{"pid": r.pid, "ppid": r.ppid, "command": r.cmd} for r in rows],
                    "windows_venv_launcher_note": sys.platform == "win32",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not rows:
            print("Процессов python -m aidd на этой машине не найдено.")
        else:
            print(
                f"Процессов ОС с «-m aidd» (python): {len(rows)}; "
                f"логических экземпляров бота: {len(logical)}."
            )
            if sys.platform == "win32" and len(rows) == 2 and len(logical) == 1:
                print(_WINDOWS_VENV_NOTE)
            for r in rows:
                role = ""
                if r.pid not in {x.pid for x in logical}:
                    role = " (лаунчер venv, см. выше)"
                print(f"  PID {r.pid} (PPID {r.ppid}): {r.cmd[:200]}{'…' if len(r.cmd) > 200 else ''}{role}")
            if conflict:
                print(
                    "\nВнимание: несколько логических экземпляров → TelegramConflictError при long polling. "
                    "Остановите лишние: .\\make.ps1 stop-bot затем один раз .\\make.ps1 run",
                    file=sys.stderr,
                )
    return 1 if conflict else 0


def cmd_stop(*, json_out: bool) -> int:
    from aidd.mcp_stop import terminate_pids

    rows = list_aidd_python_rows()
    pids = [r.pid for r in rows]
    if not pids:
        msg = {"ok": True, "stopped": [], "note": "нечего останавливать"}
        if json_out:
            print(json.dumps(msg, ensure_ascii=False))
        else:
            print("Процессов python -m aidd не найдено.")
        return 0

    if not json_out:
        print(f"Завершаю PID (все связанные процессы ОС): {pids}")
    win = sys.platform == "win32"
    killed, errors = terminate_pids(pids, force=win)
    ok = not errors
    payload = {"ok": ok, "stopped": killed, "errors": errors or None}
    if json_out:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if killed:
            print(f"Готово: завершены {killed}.")
        for e in errors:
            print(f"Ошибка: {e}", file=sys.stderr)
    return 0 if ok else 1


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(
        description="Проверка / остановка лишних экземпляров бота (python -m aidd)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Вывод в JSON (stdout)",
    )
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser(
        "check",
        help="Показать PID; exit 1 только если логических экземпляров больше одного",
    )
    sub.add_parser("stop", help="Завершить все найденные процессы (Windows: taskkill /F)")
    args = p.parse_args()
    if args.action == "check":
        raise SystemExit(cmd_check(json_out=args.json))
    raise SystemExit(cmd_stop(json_out=args.json))


if __name__ == "__main__":
    main()
