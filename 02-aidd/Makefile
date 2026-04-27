# Локальный запуск (дублируется в make.ps1 для PowerShell: .\make.ps1 install | run).
.PHONY: install run docker-build docker-up

install:
	uv sync

run:
	uv run python -m aidd

docker-build:
	docker compose build

docker-up:
	docker compose up --build
