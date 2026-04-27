"""Analytics event model for lightweight product usage tracking."""

from __future__ import annotations

from sqlalchemy import BigInteger, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base, TimestampMixin


class AnalyticsEvent(TimestampMixin, Base):
    """One sanitized user interaction event.

    The table intentionally stores action metadata instead of raw message text,
    so passwords, CDEK numbers, and free-form customer messages are not logged.
    """

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    chat_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_analytics_created_at", "created_at"),
        Index("idx_analytics_user_created", "telegram_id", "created_at"),
        Index("idx_analytics_module_action_created", "module", "action", "created_at"),
    )
