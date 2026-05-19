"""Mock credit-card issuance for demos — no real banking integration."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone


def _generate_pan16() -> str:
    """16-digit PAN-like string (not guaranteed Luhn-valid; demo only)."""
    first = secrets.randbelow(9) + 1  # 1–9
    middle = "".join(str(secrets.randbelow(10)) for _ in range(14))
    last = str(secrets.randbelow(10))
    return f"{first}{middle}{last}"


def issue_mock_credit_card(application_note: str | None = None) -> dict:
    """Build a successful mock issuance payload for open_credit_card MCP tool."""
    pan = _generate_pan16()
    op_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=365 * 4)
    expiry_str = f"{expiry.month:02d}/{expiry.year % 100:02d}"

    payload: dict = {
        "ok": True,
        "operation_id": op_id,
        "card_number": pan,
        "expiry": expiry_str,
        "payment_system": "mock_visa",
        "credit_limit_rub": 150_000,
        "currency": "RUB",
        "note": (
            "Эмуляция открытия кредитной карты; номер и лимит вымышленные, "
            "реальных операций в АБС не выполняется."
        ),
    }
    if application_note:
        payload["application_note"] = application_note
    return payload
