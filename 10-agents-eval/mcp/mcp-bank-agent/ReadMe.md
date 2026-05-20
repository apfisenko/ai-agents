# mcp-bank-agent

Локальный MCP-сервер (FastMCP, **streamable HTTP**, по умолчанию `http://127.0.0.1:8000/mcp`).

## Запуск

Из **корня** репозитория `08-mcp`:

```bash
make run-mcp-bank
# или: .\make.ps1 run-mcp-bank
```

Проверка доступности с той же машины, что и бот (читает `.env` корня): `make check-mcp-bank`.

Остановка listen-процесса на порту (часто 8000): `make stop-mcp-bank` из корня репозитория.

Вручную из этого каталога:

```bash
uv sync
uv run mcp-bank-agent
```

## Инструменты

- **`search_products`** — каталог продуктов (`data/bank_products.json`, путь через `BANK_PRODUCTS_PATH`).
- **`currency_converter_mcp`** — курсы ЦБ РФ (JSON [cbr-xml-daily.ru](https://www.cbr-xml-daily.ru/)), пересчёт любой валюты в любую **через RUB**.
- **`loan_payment_mcp`** — ориентировочный аннуитетный платёж по сумме, годовой ставке (%) и сроку в месяцах.
- **`open_credit_card`** — **мок** открытия кредитной карты (демо): в ответе JSON полный номер карты; в логах сервера фиксируются только `operation_id` и последние 4 цифры PAN.
- **`open_deposit`** — **мок** открытия вклада по сумме (руб.), сроку (мес.) и годовой ставке (%): в ответе JSON с `operation_id`, параметрами и `estimated_interest_at_maturity_rub` (упрощённая оценка); в логах — `operation_id`, сумма и срок без лишних ПДн.

### Переменные окружения (конвертер)

| Переменная | По умолчанию | Смысл |
|------------|--------------|--------|
| `CBR_DAILY_JSON_URL` | `https://www.cbr-xml-daily.ru/latest.js` | Endpoint JSON |
| `MCP_CBR_CACHE_SECONDS` | `60` | Кэш ответа API (сек), `0` — без кэша |
| `MCP_CBR_HTTP_TIMEOUT` | `15` | Таймаут HTTP, сек |

Остальное: `MCP_BANK_HOST`, `MCP_BANK_PORT`, `MCP_BANK_LOG_LEVEL`.
