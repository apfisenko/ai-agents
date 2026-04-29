from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TransactionDirection(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class OperationType(str, Enum):
    """Тип операции: повседневная / периодическая / разовая."""

    EVERYDAY = "everyday"
    PERIODIC = "periodic"
    ONE_OFF = "one_off"


class ExtractedTransaction(BaseModel):
    """Одна операция из structured output модели."""

    operation_date: Optional[str] = Field(
        default=None,
        description="Дата операции YYYY-MM-DD; если в тексте не указана — оставь пустым",
    )
    operation_time: Optional[str] = Field(
        default=None,
        description="Время HH:MM при наличии в тексте; иначе пусто",
    )
    direction: TransactionDirection
    amount: float = Field(ge=0)
    currency: Optional[str] = Field(
        default=None,
        description="ISO-код валюты, если явно указан; иначе пусто (подставится дефолт)",
    )
    operation_type: OperationType
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)


class TransactionExtractionResponse(BaseModel):
    """Ответ structured output: список операций и короткий текст пользователю."""

    transactions: list[ExtractedTransaction] = Field(default_factory=list)
    reply_to_user: str = Field(
        default="",
        description="Краткий ответ пользователю: подтверждение, совет или общение, если операций нет",
    )
