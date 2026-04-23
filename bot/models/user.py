"""用户模型."""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base, TimestampMixin


class Language(str, enum.Enum):
    """用户语言枚举."""

    ZH = "zh"
    EN = "en"
    RU = "ru"


class User(TimestampMixin, Base):
    """用户表 — 存储 Telegram 用户信息和语言偏好."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[Language] = mapped_column(
        Enum(Language, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=Language.ZH,
    )
    is_blocked: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("idx_users_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, tg_id={self.telegram_id}, lang={self.language.value})>"
