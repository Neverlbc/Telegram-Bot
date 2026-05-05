"""Analytics annotation model — manual marks for promotions / launches / incidents.

Used by the dashboard to overlay vertical markers on the daily-trends chart so
spikes and dips can be cross-referenced with real-world events.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base, TimestampMixin


class AnalyticsAnnotation(TimestampMixin, Base):
    __tablename__ = "analytics_annotations"

    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        Index("idx_annotations_event_date", "event_date"),
    )
