# База с Python 3.11 и uv из GHCR — без отдельного pull с docker.io (актуально при таймаутах к registry-1.docker.io).
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ReadMe.md ./
COPY src ./src
COPY prompts ./prompts
COPY data ./data

RUN uv sync --frozen --no-cache

ENV PATH="/app/.venv/bin:${PATH}"
# Не `uv run`: при старте uv снова собирает проект и тянет hatchling с PyPI; прокси вида
# http://127.0.0.1:… из .env внутри контейнера указывает не на хост — соединение падает.
CMD ["python", "-m", "aidd"]
