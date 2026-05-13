"""Таймауты HTTP к Hugging Face Hub до первого импорта ``huggingface_hub`` (иначе дефолт 10 с и Read timeout)."""

from __future__ import annotations

import os

_DEFAULT_SECONDS = "120"


def apply_hf_hub_default_timeouts() -> None:
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", _DEFAULT_SECONDS)
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", _DEFAULT_SECONDS)


apply_hf_hub_default_timeouts()
