"""Инструмент `convert_currency`: ориентировочный пересчёт суммы по внешнему публичному API курсов (не курс банка)."""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

CONVERT_CURRENCY_TOOL_NAME = "convert_currency"

_CURRENCY_CODE_RE = re.compile(r"^[A-Za-z]{3}$")

_CURRENCY_TOOL_DESCRIPTION = (
    "Пересчитывает сумму из одной валюты в другую по актуальному ориентировочному рыночному курсу "
    "(не курс обмена конкретного банка и не оферта). "
    "Коды — ISO 4217, три латинские буквы (например USD, RUB, EUR). "
    "Используй, когда пользователь просит перевести сумму, узнать эквивалент или сравнить валюты; "
    "не вызывай для вопросов только по продуктам банка без пересчёта — тогда при необходимости rag_search."
)


def _normalize_code(code: str) -> str | None:
    c = (code or "").strip().upper()
    return c if c and _CURRENCY_CODE_RE.match(c) else None


def make_convert_currency_tool():
    """LangChain tool без состояния (один общий httpx-клиент создаётся на вызов — KISS)."""

    @tool(CONVERT_CURRENCY_TOOL_NAME, description=_CURRENCY_TOOL_DESCRIPTION)
    async def convert_currency(
        amount: Annotated[float, "Сумма в исходной валюте (число больше нуля)."],
        from_currency: Annotated[str, "ISO 4217: исходная валюта, три буквы (USD, EUR, RUB, …)."],
        to_currency: Annotated[str, "ISO 4217: целевая валюта, три буквы."],
    ) -> str:
        def _error(msg: str) -> str:
            return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)

        try:
            amt = float(amount)
        except (TypeError, ValueError):
            return _error("Некорректная сумма.")

        if amt <= 0:
            return _error("Сумма должна быть больше нуля.")

        frm = _normalize_code(from_currency)
        to = _normalize_code(to_currency)
        if not frm or not to:
            return _error("Укажите корректные трёхбуквенные коды валют (ISO 4217).")

        if frm == to:
            return json.dumps(
                {
                    "ok": True,
                    "from_currency": frm,
                    "to_currency": to,
                    "amount": amt,
                    "rate": 1.0,
                    "result": round(amt, 6),
                    "note": "Одинаковая валюта; пересчёт не требуется.",
                },
                ensure_ascii=False,
            )

        url = f"https://latest.currency-api.pages.dev/v1/currencies/{frm.lower()}.json"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
        except Exception:
            logger.exception("convert_currency: HTTP failed url=%s", url)
            return _error("Не удалось получить курс. Попробуйте позже.")

        block = data.get(frm.lower()) if isinstance(data, dict) else None
        if not isinstance(block, dict):
            return _error("Неожиданный формат ответа сервиса курсов.")

        raw_rate = block.get(to.lower())
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            return _error(f"Курс {frm} → {to} недоступен в сервисе.")

        if rate <= 0:
            return _error("Получен некорректный курс.")

        result = round(amt * rate, 6)
        payload = {
            "ok": True,
            "from_currency": frm,
            "to_currency": to,
            "amount": amt,
            "rate": rate,
            "result": result,
            "note": (
                "Ориентировочный рыночный курс из публичного API; для операций в банке уточняйте актуальный курс в отделении или в приложении."
            ),
        }
        logger.debug(
            "convert_currency: %s %.4f -> %s rate=%.6f",
            frm,
            amt,
            to,
            rate,
        )
        return json.dumps(payload, ensure_ascii=False)

    return convert_currency
