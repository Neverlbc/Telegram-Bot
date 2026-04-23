"""FAQ 与配送说明数据服务."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.faq import FaqItem, FaqType


async def get_faq_list(session: AsyncSession) -> list[FaqItem]:
    """获取所有激活的 FAQ 条目, 按 sort_order 排序."""
    stmt = (
        select(FaqItem)
        .where(FaqItem.type == FaqType.FAQ, FaqItem.is_active.is_(True))
        .order_by(FaqItem.sort_order)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_delivery_list(session: AsyncSession) -> list[FaqItem]:
    """获取所有激活的配送说明条目, 按 sort_order 排序."""
    stmt = (
        select(FaqItem)
        .where(FaqItem.type == FaqType.DELIVERY, FaqItem.is_active.is_(True))
        .order_by(FaqItem.sort_order)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_faq_item_by_id(session: AsyncSession, item_id: int) -> FaqItem | None:
    """按 ID 获取 FAQ 条目."""
    stmt = select(FaqItem).where(FaqItem.id == item_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
