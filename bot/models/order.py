"""订单相关模型."""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base, TimestampMixin


class OrderStatus(str, enum.Enum):
    """批发订单状态."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WholesaleOrder(TimestampMixin, Base):
    """批发订单表."""

    __tablename__ = "wholesale_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OrderStatus.PENDING,
    )
    agent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assigned_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_wholesale_user_id", "user_id"),
        Index("idx_wholesale_status", "status"),
        Index("idx_wholesale_created_at", "created_at"),
    )


class AftersaleQuery(TimestampMixin, Base):
    """售后查询记录表."""

    __tablename__ = "aftersale_queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    query_count: Mapped[int] = mapped_column(default=1, nullable=False)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    escalated: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_queried_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_aftersale_user_id", "user_id"),
        Index("uq_aftersale_user_order", "user_id", "order_id", unique=True),
    )


class CarrierType(str, enum.Enum):
    """物流商枚举."""

    CDEK = "cdek"
    RUPOST = "rupost"
    CAINIAO = "cainiao"
    AIRFREIGHT = "airfreight"
    CHINA_DOMESTIC = "china_domestic"


class OriginType(str, enum.Enum):
    """发货地枚举."""

    MOSCOW = "moscow"
    CHINA = "china"


class LogisticsQuery(TimestampMixin, Base):
    """物流查询记录表."""

    __tablename__ = "logistics_queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tracking_no: Mapped[str] = mapped_column(String(128), nullable=False)
    carrier: Mapped[CarrierType] = mapped_column(
        Enum(CarrierType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    origin: Mapped[OriginType] = mapped_column(
        Enum(OriginType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    result_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_queried_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)
    query_count: Mapped[int] = mapped_column(default=1, nullable=False)

    __table_args__ = (
        Index("idx_logistics_user_id", "user_id"),
        Index("idx_logistics_tracking_no", "tracking_no"),
        Index("uq_logistics_user_tracking", "user_id", "tracking_no", "carrier", unique=True),
    )
