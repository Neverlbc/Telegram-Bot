"""速卖通店铺 Cookie 存储模型."""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.models import Base, TimestampMixin


class AEStoreCookie(TimestampMixin, Base):
    """存储各速卖通店铺的登录 Cookie，用于 MTOP 接口鉴权。"""

    __tablename__ = "ae_store_cookies"

    store_name: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, index=True
    )
    cookie: Mapped[str] = mapped_column(Text, nullable=False, default="")
    channel_id: Mapped[str] = mapped_column(Text, nullable=False, default="238299")
