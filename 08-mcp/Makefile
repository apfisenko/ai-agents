# Локальный запуск (дублируется в make.ps1 для PowerShell: .\make.ps1 install | run).
.PHONY: install run run-mcp-bank stop-mcp-bank check-mcp-bank check-bot stop-bot smoke-index smoke-rag-chain dataset dataset-upload docker-build docker-up docker-down docker-up-host docker-down-host docker-ps docker-check docker-windows-host-ip docker-portproxy-hint portproxy-up portproxy-down

install:
	uv sync

run:
	uv run python -m aidd

# MCP-сервер банка (ит.24): терминал 1 — make run-mcp-bank; терминал 2 — make run. URL в .env: MCP_BANK_STREAMABLE_HTTP_URL
run-mcp-bank:
	cd mcp/mcp-bank-agent && uv sync && uv run mcp-bank-agent

check-mcp-bank:
	uv run python -m aidd.mcp_health check

# Завершить процесс(ы) на порту MCP (MCP_BANK_PORT или порт из MCP_BANK_STREAMABLE_HTTP_URL; иначе 8000). Осторожно: на порту может быть не только mcp-bank-agent
stop-mcp-bank:
	uv run python -m aidd.mcp_stop

# TelegramConflictError при нескольких логических ботах; на Windows один .\\make.ps1 run часто = 2 PID ОС (лаунчер venv + интерпретатор). См. check-bot / stop-bot
check-bot:
	uv run python -m aidd.bot_processes check

stop-bot:
	uv run python -m aidd.bot_processes stop

# Smoke RAG-индексации (итерация 5): нужны OPEN_API_KEY, OPEN_BASE_URL; опционально EMBEDDING_MODEL
smoke-index:
	uv run python -m aidd.smoke_index

# Регрессия RAG-цепочки (ит.15): полный AppConfig из .env, индекс, один ainvoke (диалог как в боте)
smoke-rag-chain:
	uv run python -m aidd.smoke_rag_chain

# Датасет Q&A для RAGAS / LangSmith (итерация 10): нужны OPEN_* и LLM_*; см. docs/vision.md §10
dataset:
	uv run python -m aidd.dataset_synthesizer synthesize

dataset-upload:
	uv run python -m aidd.dataset_synthesizer upload

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-up-host:
	docker compose -f docker-compose.yml -f docker-compose.host-network.yml up --build

docker-down-host:
	docker compose -f docker-compose.yml -f docker-compose.host-network.yml down

docker-ps:
	docker compose ps -a

docker-check:
	docker compose exec -T bot true

docker-windows-host-ip:
	@echo "Windows+WSL: из PowerShell выполните .\\make.ps1 docker-windows-host-ip"

docker-portproxy-hint:
	@echo "Windows+WSL: netsh portproxy — из PowerShell выполните: .\\make.ps1 docker-portproxy-hint"
	@echo "Иначе: ReadMe, раздел про ClientProxyConnectionError (Allow LAN, portproxy)."

# Только Windows (PowerShell + админ): включить/выключить portproxy+firewall, см. ReadMe
portproxy-up portproxy-down:
	@echo "Из PowerShell (админ): .\\make.ps1 $@"
	@echo "Опции: -ListenPort 11301 -ConnectPort 1301"
