"""商品目录数据服务 — Category / Product / Variant 查询."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models.product import Category, Product, ProductVariant


async def get_top_categories(session: AsyncSession) -> list[Category]:
    """获取所有顶级分类 (parent_id IS NULL), 按 sort_order 排序."""
    stmt = (
        select(Category)
        .where(Category.parent_id.is_(None), Category.is_active.is_(True))
        .order_by(Category.sort_order)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_subcategories(session: AsyncSession, parent_id: int) -> list[Category]:
    """获取某分类下的子分类."""
    stmt = (
        select(Category)
        .where(Category.parent_id == parent_id, Category.is_active.is_(True))
        .order_by(Category.sort_order)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_category_by_id(session: AsyncSession, category_id: int) -> Category | None:
    """按 ID 获取分类."""
    stmt = select(Category).where(Category.id == category_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_products_by_category(
    session: AsyncSession, category_id: int, page: int = 1, page_size: int = 8,
) -> tuple[list[Product], int]:
    """获取某分类下的商品列表 (分页).

    Returns:
        (products, total_count)
    """
    # 总数
    from sqlalchemy import func

    count_stmt = (
        select(func.count())
        .select_from(Product)
        .where(Product.category_id == category_id, Product.is_active.is_(True))
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    # 分页数据
    offset = (page - 1) * page_size
    stmt = (
        select(Product)
        .where(Product.category_id == category_id, Product.is_active.is_(True))
        .order_by(Product.sort_order)
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all()), int(total)


async def get_product_by_id(session: AsyncSession, product_id: int) -> Product | None:
    """按 ID 获取商品，包含预加载的 variants."""
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.variants))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_variant_by_id(session: AsyncSession, variant_id: int) -> ProductVariant | None:
    """按 ID 获取商品规格."""
    stmt = select(ProductVariant).where(ProductVariant.id == variant_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
