#!/usr/bin/env bash
# Аналог Makefile / make.ps1 для POSIX (Linux, macOS, Git Bash). Из корня: bash make.sh run | bash make.sh help
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

target="${1:-help}"
if [[ "${#}" -ge 1 ]]; then
  shift
fi

case "$target" in
  install)
    uv sync
    ;;
  run)
    uv run python -m aidd
    ;;
  run-mcp-bank)
    (cd "${ROOT}/mcp/mcp-bank-agent" && uv sync && uv run mcp-bank-agent)
    ;;
  check-mcp-bank)
    uv run python -m aidd.mcp_health check
    ;;
  stop-mcp-bank)
    uv run python -m aidd.mcp_stop
    ;;
  check-bot)
    uv run python -m aidd.bot_processes check
    ;;
  stop-bot)
    uv run python -m aidd.bot_processes stop
    ;;
  smoke-index)
    uv run python -m aidd.smoke_index
    ;;
  smoke-rag-chain)
    uv run python -m aidd.smoke_rag_chain
    ;;
  dataset)
    uv run python -m aidd.dataset_synthesizer synthesize
    ;;
  dataset-upload)
    uv run python -m aidd.dataset_synthesizer upload
    ;;
  test-e2e-agent)
    uv sync --group dev
    uv run pytest tests/e2e -q
    ;;
  test-e2e-agent-deterministic)
    uv sync --group dev
    uv run pytest tests/e2e/test_agent_e2e_deterministic.py -q
    ;;
  test-e2e-agent-judge)
    uv sync --group dev
    uv run pytest tests/e2e/test_agent_e2e_llm_judge.py -q
    ;;
  docker-build)
    docker compose build "$@"
    ;;
  docker-up)
    docker compose up --build "$@"
    ;;
  docker-down)
    docker compose down "$@"
    ;;
  docker-up-host)
    docker compose -f docker-compose.yml -f docker-compose.host-network.yml up --build "$@"
    ;;
  docker-down-host)
    docker compose -f docker-compose.yml -f docker-compose.host-network.yml down "$@"
    ;;
  docker-ps)
    docker compose ps -a "$@"
    ;;
  docker-check)
    docker compose exec -T bot true "$@"
    ;;
  docker-windows-host-ip)
    echo "Windows+WSL: из PowerShell выполните .\\make.ps1 docker-windows-host-ip"
    ;;
  docker-portproxy-hint)
    echo "Windows+WSL: netsh portproxy — из PowerShell выполните: .\\make.ps1 docker-portproxy-hint"
    echo "Иначе: ReadMe, раздел про ClientProxyConnectionError (Allow LAN, portproxy)."
    ;;
  portproxy-up | portproxy-down)
    echo "Только Windows (PowerShell от администратора): .\\make.ps1 ${target}"
    echo "Опции: -ListenPort 11301 -ConnectPort 1301"
    ;;
  help | *)
    echo "Usage: bash make.sh <target>"
    echo "  install | run | run-mcp-bank | check-mcp-bank | stop-mcp-bank"
    echo "  check-bot | stop-bot"
    echo "  smoke-index | smoke-rag-chain"
    echo "  dataset | dataset-upload"
    echo "  test-e2e-agent | test-e2e-agent-deterministic | test-e2e-agent-judge"
    echo "  docker-build | docker-up | docker-down | docker-up-host | docker-down-host"
    echo "  docker-ps | docker-check"
    echo "  docker-windows-host-ip | docker-portproxy-hint | portproxy-up | portproxy-down"
    ;;
esac
