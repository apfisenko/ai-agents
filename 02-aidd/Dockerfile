# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-cache

COPY ReadMe.md ./
COPY src ./src
COPY prompts ./prompts

RUN uv sync --frozen --no-cache

CMD ["uv", "run", "python", "-m", "aidd"]
