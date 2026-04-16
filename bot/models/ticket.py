"""客服工单相关模型."""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base, TimestampMixin


class TicketType(str, enum.Enum):
    """工单类型."""

    GENERAL = "general"
    BUSINESS = "business"
    WHOLESALE = "wholesale"
    AFTERSALE = "aftersale"
    LOGISTICS = "logistics"


class TicketStatus(str, enum.Enum):
    """工单状态."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class SenderRole(str, enum.Enum):
    """消息发送者角色."""

    USER = "user"
    AGENT = "agent"


class MessageType(str, enum.Enum):
    """消息类型."""

    TEXT = "text"
    PHOTO = "photo"
    DOCUMENT = "document"
    VOICE = "voice"


class SupportTicket(TimestampMixin, Base):
    """客服工单表."""

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[TicketType] = mapped_column(
        Enum(TicketType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TicketStatus.PENDING,
    )
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ref_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_ticket_user_id", "user_id"),
        Index("idx_ticket_agent_status", "agent_id", "status"),
        Index("idx_ticket_status", "status"),
    )


class SupportMessage(Base):
    """客服消息记录表."""

    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_role: Mapped[SenderRole] = mapped_column(
        Enum(SenderRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MessageType.TEXT,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_message_ticket_id", "ticket_id"),
        Index("idx_message_created_at", "created_at"),
    )
