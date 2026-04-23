"""设备支持相关模型."""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base, TimestampMixin


class DeviceSection(str, enum.Enum):
    """设备问题来源."""

    ISSUE = "issue"
    MORE = "more"


class DeviceIssueType(str, enum.Enum):
    """设备问题类型."""

    FIRMWARE = "firmware"
    HARDWARE = "hardware"
    SOFTWARE = "software"
    REMOTE = "remote"


class DeviceTicketStatus(str, enum.Enum):
    """设备工单状态."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ESCALATED = "escalated"


class DeviceHandler(str, enum.Enum):
    """处理方式."""

    ROBOT = "robot"
    HUMAN = "human"


class DeviceSerialQuery(TimestampMixin, Base):
    """序列号查询记录表."""

    __tablename__ = "device_serial_queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    serial_no: Mapped[str] = mapped_column(String(128), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    product_info: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    found: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("idx_device_serial_user_id", "user_id"),
        Index("idx_device_serial_no", "serial_no"),
    )


class DeviceTicket(TimestampMixin, Base):
    """设备问题工单表."""

    __tablename__ = "device_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[DeviceSection] = mapped_column(
        Enum(DeviceSection, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    issue_type: Mapped[DeviceIssueType] = mapped_column(
        Enum(DeviceIssueType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DeviceTicketStatus] = mapped_column(
        Enum(DeviceTicketStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DeviceTicketStatus.PENDING,
    )
    handler: Mapped[DeviceHandler | None] = mapped_column(
        Enum(DeviceHandler, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_device_ticket_user_id", "user_id"),
        Index("idx_device_ticket_status", "status"),
        Index("idx_device_ticket_section_type", "section", "issue_type"),
    )
