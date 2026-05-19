"""Определение запуска внутри контейнера (Docker / Compose)."""

from __future__ import annotations

import os
from pathlib import Path


def is_docker_container() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("AIDD_DOCKER", "").strip() == "1"
