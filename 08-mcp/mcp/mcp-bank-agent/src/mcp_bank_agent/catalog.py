from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        msg = f"Файл каталога не найден: {path}"
        raise FileNotFoundError(msg)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    products = data.get("products")
    if not isinstance(products, list):
        msg = "Ожидался ключ 'products' со списком в JSON"
        raise ValueError(msg)
    return products


def _product_blob(product: dict[str, Any]) -> str:
    promos = product.get("promotions") or []
    tags = product.get("tags") or []
    if isinstance(promos, list):
        promos_text = " ".join(str(x) for x in promos)
    else:
        promos_text = str(promos)
    if isinstance(tags, list):
        tags_text = " ".join(str(x) for x in tags)
    else:
        tags_text = str(tags)
    parts = [
        str(product.get("name", "")),
        str(product.get("description", "")),
        str(product.get("type", "")),
        json.dumps(product.get("conditions", {}), ensure_ascii=False),
        promos_text,
        tags_text,
    ]
    return " ".join(parts).lower()


def _tokens(query: str) -> list[str]:
    return [t for t in re.split(r"\s+", query.strip().lower()) if t]


def search_products(
    products: list[dict[str, Any]],
    *,
    query: str,
    product_type: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Простой поиск: все токены из query должны встречаться в объединённом тексте карточки."""
    tokens = _tokens(query)
    type_key = (product_type or "").strip().lower() or None
    out: list[dict[str, Any]] = []
    for p in products:
        if type_key and str(p.get("type", "")).strip().lower() != type_key:
            continue
        blob = _product_blob(p)
        if not tokens or all(t in blob for t in tokens):
            out.append(p)
        if len(out) >= limit:
            break
    return out
