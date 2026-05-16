from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastmcp import FastMCP

from mcp_bank_agent.catalog import load_catalog
from mcp_bank_agent.catalog import search_products as filter_products
from mcp_bank_agent.cbr_convert import convert_via_rub

logging.basicConfig(
    level=os.environ.get("MCP_BANK_LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
log = logging.getLogger("mcp_bank_agent")

mcp = FastMCP(
    "mcp-bank-agent",
    instructions=(
        "Инструменты банковского ассистента: search_products — карточки продуктов из каталога; "
        "currency_converter_mcp — пересчёт валют по курсам ЦБ РФ (JSON cbr-xml-daily.ru), "
        "любая ISO-валюта в любую через RUB."
    ),
)

_products: list[dict] | None = None


def _default_data_path() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "bank_products.json"


def _data_path() -> Path:
    env = os.environ.get("BANK_PRODUCTS_PATH")
    if env:
        return Path(env)
    return _default_data_path()


def get_products() -> list[dict]:
    global _products
    if _products is None:
        path = _data_path()
        log.info("Loading product catalog from %s", path)
        _products = load_catalog(path)
    return _products


@mcp.tool
def search_products(
    query: str,
    product_type: str | None = None,
    limit: int = 10,
) -> str:
    """Ищет продукты банка по каталогу (вклады, кредиты, дебетовые/кредитные карты, счета).

    Учитываются название, описание, тип, условия (ставки, сроки, валюты), акции и теги.
    Параметр product_type, если задан, должен совпадать с полем type карточки: deposit, loan,
    debit_card, credit_card, account.

    Возвращает JSON строку: { "count", "products" }.
    """
    lim = max(1, min(int(limit), 50))
    matches = filter_products(
        get_products(),
        query=query or "",
        product_type=product_type,
        limit=lim,
    )
    payload = {"count": len(matches), "products": matches}
    return json.dumps(payload, ensure_ascii=False)


def _round_conv_payload(payload: dict) -> dict:
    out = dict(payload)
    if "result" in out and isinstance(out["result"], (int, float)):
        out["result"] = round(float(out["result"]), 10)
    ir = out.get("intermediate_rub")
    if ir is not None and isinstance(ir, (int, float)):
        out["intermediate_rub"] = round(float(ir), 10)
    return out


@mcp.tool
def currency_converter_mcp(amount: float, from_currency: str, to_currency: str) -> str:
    """Конвертация суммы по курсам ЦБ РФ на дату ответа API (обёртка cbr-xml-daily.ru).

    Любая поддерживаемая API валюта → любая через промежуточную оценку в RUB.
    Коды валют — ISO 4217 (например USD, EUR, RUB, KZT). Для RUB используйте RUB.

    Возвращает JSON: при успехе ok=true, date, from_currency, to_currency, amount, result,
    via_rub, intermediate_rub (при пересчёте через RUB), note; при ошибке ok=false, error.
    """
    try:
        raw = convert_via_rub(float(amount), from_currency, to_currency)
        payload = _round_conv_payload(raw)
        return json.dumps(payload, ensure_ascii=False)
    except (RuntimeError, KeyError, ValueError) as e:
        err = {"ok": False, "error": str(e)}
        return json.dumps(err, ensure_ascii=False)


def main() -> None:
    host = os.environ.get("MCP_BANK_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_BANK_PORT", "8000"))
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
