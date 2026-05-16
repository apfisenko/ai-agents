"""Курсы ЦБ РФ через JSON API cbr-xml-daily.ru; пересчёт любая→любая через RUB."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_CBR_JSON_URL = "https://www.cbr-xml-daily.ru/latest.js"

_cache_payload: dict[str, Any] | None = None
_cache_mono: float = 0.0


def _cache_ttl_sec() -> int:
    return max(0, int(os.environ.get("MCP_CBR_CACHE_SECONDS", "60")))


def _normalize_iso_code(code: str) -> str:
    c = (code or "").strip().upper()
    if len(c) != 3 or not c.isalpha():
        msg = f"Ожидался код валюты ISO 4217 из трёх букв, получено: {code!r}"
        raise ValueError(msg)
    return c


def fetch_daily_json(url: str | None = None) -> dict[str, Any]:
    """Загружает JSON с полями date, base (=RUB), rates: { CODE: units_per_one_rub }."""
    endpoint = url or os.environ.get("CBR_DAILY_JSON_URL") or DEFAULT_CBR_JSON_URL
    timeout = float(os.environ.get("MCP_CBR_HTTP_TIMEOUT", "15"))
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(endpoint)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        msg = f"HTTP-ошибка при запросе курсов ЦБ: {e}"
        log.warning("%s", msg)
        raise RuntimeError(msg) from e
    except ValueError as e:
        msg = f"Некорректный JSON ответа курсов: {e}"
        log.warning("%s", msg)
        raise RuntimeError(msg) from e

    rates = data.get("rates")
    if not isinstance(rates, dict):
        msg = "В ответе API отсутствует объект rates"
        raise RuntimeError(msg)
    data_date = data.get("date")
    if data_date is None:
        data_date = data.get("Date")  # на случай другой формы
    return {"date": data_date, "base": data.get("base", "RUB"), "rates": rates}


def get_rates_payload() -> dict[str, Any]:
    ttl = _cache_ttl_sec()
    global _cache_payload, _cache_mono
    now = time.monotonic()
    if _cache_payload is not None and ttl > 0 and (now - _cache_mono) < ttl:
        return _cache_payload
    _cache_payload = fetch_daily_json()
    _cache_mono = now
    return _cache_payload


def _to_rub(amount: float, currency: str, rates: dict[str, Any]) -> float:
    """Сумма в валюте currency → RUB. Курс: units_foreign_per_1_rub."""
    if currency == "RUB":
        return amount
    rate = rates.get(currency)
    if rate is None:
        msg = f"Валюта {currency} отсутствует в котировках ЦБ на выбранную дату"
        raise KeyError(msg)
    rate_f = float(rate)
    if rate_f <= 0:
        msg = f"Некорректный курс для {currency}"
        raise ValueError(msg)
    return amount / rate_f


def _from_rub(amount_rub: float, currency: str, rates: dict[str, Any]) -> float:
    """RUB → валюта currency."""
    if currency == "RUB":
        return amount_rub
    rate = rates.get(currency)
    if rate is None:
        msg = f"Валюта {currency} отсутствует в котировках ЦБ на выбранную дату"
        raise KeyError(msg)
    rate_f = float(rate)
    if rate_f <= 0:
        msg = f"Некорректный курс для {currency}"
        raise ValueError(msg)
    return amount_rub * rate_f


def convert_via_rub(
    amount: float,
    from_currency: str,
    to_currency: str,
    *,
    rates: dict[str, Any] | None = None,
    rate_date: str | None = None,
) -> dict[str, Any]:
    """Пересчёт amount из from_currency в to_currency через RUB."""
    if amount <= 0:
        msg = "Сумма должна быть положительным числом"
        raise ValueError(msg)
    fc = _normalize_iso_code(from_currency)
    tc = _normalize_iso_code(to_currency)

    payload = get_rates_payload() if rates is None else {"rates": rates, "date": rate_date}
    rts: dict[str, Any] = payload["rates"]
    d = payload.get("date")

    if fc == tc:
        return {
            "ok": True,
            "date": d,
            "from_currency": fc,
            "to_currency": tc,
            "amount": amount,
            "result": amount,
            "via_rub": False,
            "intermediate_rub": None,
            "note": "Исходная и целевая валюты совпадают.",
        }

    rub = _to_rub(amount, fc, rts)
    result = _from_rub(rub, tc, rts)
    return {
        "ok": True,
        "date": d,
        "from_currency": fc,
        "to_currency": tc,
        "amount": amount,
        "result": result,
        "via_rub": True,
        "intermediate_rub": rub,
        "note": "Курсы официальные ЦБ РФ на дату ответа API (источник: cbr-xml-daily.ru). Не курс обмена в отделении банка.",
    }
