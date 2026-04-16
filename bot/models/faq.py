"""FAQ 与配送说明模型."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base


class FaqType(str, enum.Enum):
    """FAQ 条目类型."""

    FAQ = "faq"
    DELIVERY = "delivery"


class FaqItem(Base):
    """FAQ 与配送说明表 — 统一存储两类内容."""

    __tablename__ = "faq_items"

    type: Mapped[FaqType] = mapped_column(
        Enum(FaqType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    question_zh: Mapped[str | None] = mapped_column(String(256), nullable=True)
    question_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    question_ru: Mapped[str | None] = mapped_column(String(256), nullable=True)
    answer_zh: Mapped[str] = mapped_column(Text, nullable=False)
    answer_en: Mapped[str] = mapped_column(Text, nullable=False)
    answer_ru: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    updated_at: Mapped[str | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_faq_type_active", "type", "is_active", "sort_order"),
    )

    def get_question(self, lang: str = "zh") -> str | None:
        """根据语言获取问题."""
        return getattr(self, f"question_{lang}", self.question_zh)

    def get_answer(self, lang: str = "zh") -> str:
        """根据语言获取答案."""
        return getattr(self, f"answer_{lang}", self.answer_zh)
