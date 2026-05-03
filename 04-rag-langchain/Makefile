# Локальный запуск (дублируется в make.ps1 для PowerShell: .\make.ps1 install | run).
.PHONY: install run smoke-index docker-build docker-up docker-down docker-up-host docker-down-host docker-ps docker-check docker-windows-host-ip docker-portproxy-hint portproxy-up portproxy-down

install:
	uv sync

run:
	uv run python -m aidd

# Smoke RAG-индексации (итерация 5): нужны OPEN_API_KEY, OPEN_BASE_URL; опционально EMBEDDING_MODEL
smoke-index:
	uv run python -m aidd.smoke_index

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
