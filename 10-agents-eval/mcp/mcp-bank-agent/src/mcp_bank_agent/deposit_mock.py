"""Mock deposit opening for demos — no real banking integration."""

from __future__ import annotations

import uuid


def issue_mock_deposit(
    amount_rub: float,
    term_months: int,
    annual_rate_percent: float,
    application_note: str | None = None,
) -> dict:
    """Build a successful mock deposit payload for open_deposit MCP tool."""
    principal = round(float(amount_rub), 2)
    term = int(term_months)
    rate = float(annual_rate_percent)
    # Упрощённая оценка простых процентов на срок (не капитализация, не налоги).
    interest = principal * (rate / 100.0) * (term / 12.0)
    interest_rub = round(float(interest), 2)

    op_id = str(uuid.uuid4())
    payload: dict = {
        "ok": True,
        "operation_id": op_id,
        "amount_rub": principal,
        "term_months": term,
        "annual_rate_percent": round(rate, 6),
        "currency": "RUB",
        "estimated_interest_at_maturity_rub": interest_rub,
        "note": (
            "Эмуляция открытия вклада; суммы и ставка вымышленные для демо, "
            "реальных операций в АБС не выполняется."
        ),
    }
    if application_note:
        payload["application_note"] = application_note
    return payload
