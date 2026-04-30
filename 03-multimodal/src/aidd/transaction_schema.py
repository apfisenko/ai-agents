from __future__ import annotations

from enum import Enum
from typing import Optional, Self

from pydantic import BaseModel, Field, model_validator


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
    amount: float = Field(
        ge=0,
        description="Число; из голоса — переведи числительное в цифру (триста → 300)",
    )
    currency: Optional[str] = Field(
        default=None,
        description="ISO-код валюты, если явно указан; иначе пусто (подставится дефолт)",
    )
    operation_type: OperationType = Field(
        description=(
            "everyday для обычной разовой траты без явной регулярности; "
            "periodic только при подписке или регулярных платежах в реплике"
        ),
    )
    category: str = Field(
        default="",
        description=(
            "Тема как сказал пользователь; если модель вернула пусто — подставится «прочее» при сохранении"
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description="Краткий смысл траты; если нет — дубль категории",
    )

    @model_validator(mode="after")
    def _ensure_category_and_description(self) -> Self:
        cat = (self.category or "").strip() or "прочее"
        desc = (self.description or "").strip() or cat
        return self.model_copy(update={"category": cat, "description": desc})


class TransactionExtractionResponse(BaseModel):
    """Ответ structured output: список операций и короткий текст пользователю."""

    transactions: list[ExtractedTransaction] = Field(default_factory=list)
    reply_to_user: str = Field(
        default="",
        description=(
            "Краткое подтверждение с той же суммой и темой, что в transactions; без советов про несуществующие категории"
        ),
    )
