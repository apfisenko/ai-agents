from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List

from aidd.transaction_schema import ExtractedTransaction, OperationType, TransactionDirection


@dataclass(frozen=True)
class TransactionRecord:
    operation_date: date
    operation_time: str | None
    direction: TransactionDirection
    amount: float
    currency: str
    operation_type: OperationType
    category: str
    description: str


def records_from_extracted(
    items: list[ExtractedTransaction],
    fallback_date: date,
    default_currency: str,
) -> list[TransactionRecord]:
    """Преобразует извлечённые моделью поля в записи учёта с дефолтной датой/валютой."""
    out: list[TransactionRecord] = []
    for ex in items:
        d = fallback_date
        raw_date = (ex.operation_date or "").strip()
        if raw_date:
            try:
                y, m, day = raw_date.split("-")
                d = date(int(y), int(m), int(day))
            except (ValueError, AttributeError):
                d = fallback_date
        cur = (ex.currency or "").strip() or default_currency
        ot = (ex.operation_time or "").strip() or None
        out.append(
            TransactionRecord(
                operation_date=d,
                operation_time=ot,
                direction=ex.direction,
                amount=ex.amount,
                currency=cur,
                operation_type=ex.operation_type,
                category=ex.category.strip(),
                description=ex.description.strip(),
            )
        )
    return out


class TransactionStore:
    """Учёт транзакций по chat_id только в памяти процесса."""

    def __init__(self) -> None:
        self._by_chat: Dict[int, List[TransactionRecord]] = {}

    def add_many(self, chat_id: int, rows: List[TransactionRecord]) -> None:
        if not rows:
            return
        bucket = self._by_chat.setdefault(chat_id, [])
        bucket.extend(rows)

    def get_all(self, chat_id: int) -> List[TransactionRecord]:
        return list(self._by_chat.get(chat_id, []))

    def clear(self, chat_id: int) -> None:
        self._by_chat.pop(chat_id, None)


def aggregate_by_category_expenses(records: List[TransactionRecord]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in records:
        if r.direction == TransactionDirection.EXPENSE:
            out[r.category] += r.amount
    return dict(out)


def format_balance_report(records: List[TransactionRecord]) -> str:
    """Детерминированная сводка без второго вызова LLM."""
    if not records:
        return (
            "Пока нет записанных операций. Опишите трату или доход текстом — я распознаю суммы "
            "и сохраню их для отчёта."
        )
    income = sum(r.amount for r in records if r.direction == TransactionDirection.INCOME)
    expense = sum(r.amount for r in records if r.direction == TransactionDirection.EXPENSE)
    balance = income - expense
    lines = [
        "Сводка по сохранённым операциям:",
        f"• Доходы: {income:.2f}",
        f"• Расходы: {expense:.2f}",
        f"• Баланс (доходы − расходы): {balance:.2f}",
    ]
    by_cat = aggregate_by_category_expenses(records)
    if by_cat:
        lines.append("")
        lines.append("Расходы по категориям:")
        for name, total in sorted(by_cat.items(), key=lambda x: -x[1]):
            lines.append(f"  — {name}: {total:.2f}")
    return "\n".join(lines)
