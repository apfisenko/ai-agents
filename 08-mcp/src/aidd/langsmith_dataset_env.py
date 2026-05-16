"""Имя датасета LangSmith из окружения: синтез, upload, evaluate."""

from __future__ import annotations

import os
import re

_DEFAULT_DATASET_NAME = "06-rag-qa-dataset"
_UNSAFE_FOR_FILENAME = re.compile(r"[^a-zA-Z0-9._\-]+")


def langsmith_dataset_name() -> str:
    """Имя набора в LangSmith и база имени локального JSON.

    Приоритет: ``LANGSMITH_DATASET``, затем устаревший ``LANGSMITH_DATASET_NAME``, иначе дефолт.
    """
    raw = (
        os.environ.get("LANGSMITH_DATASET")
        or os.environ.get("LANGSMITH_DATASET_NAME")
        or ""
    ).strip()
    return raw or _DEFAULT_DATASET_NAME


def langsmith_dataset_json_filename() -> str:
    """Имя файла ``datasets/<stem>.json`` по ``langsmith_dataset_name()`` (безопасно для ФС)."""
    stem = _UNSAFE_FOR_FILENAME.sub("_", langsmith_dataset_name()).strip("._")
    if not stem:
        stem = _DEFAULT_DATASET_NAME
    return f"{stem}.json"
