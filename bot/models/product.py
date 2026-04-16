"""商品 & 分类模型."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models import Base, TimestampMixin


class Category(Base):
    """商品分类表 — 支持两级分类结构."""

    __tablename__ = "categories"

    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    name_zh: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[str | None] = mapped_column(nullable=True)

    # 关系
    children: Mapped[list[Category]] = relationship("Category", back_populates="parent", lazy="selectin")
    parent: Mapped[Category | None] = relationship("Category", back_populates="children", remote_side="Category.id")
    products: Mapped[list[Product]] = relationship("Product", back_populates="category", lazy="selectin")

    __table_args__ = (
        Index("idx_categories_parent_id", "parent_id"),
        Index("idx_categories_sort_active", "sort_order", "is_active"),
    )

    def get_name(self, lang: str = "zh") -> str:
        """根据语言获取分类名称."""
        return getattr(self, f"name_{lang}", self.name_zh)


class Product(TimestampMixin, Base):
    """商品表."""

    __tablename__ = "products"

    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name_zh: Mapped[str] = mapped_column(String(256), nullable=False)
    name_en: Mapped[str] = mapped_column(String(256), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(256), nullable=False)
    description_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 关系
    category: Mapped[Category] = relationship("Category", back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship("ProductVariant", back_populates="product", lazy="selectin")

    __table_args__ = (
        Index("idx_products_category_active", "category_id", "is_active"),
        Index("idx_products_sort_order", "sort_order"),
    )

    def get_name(self, lang: str = "zh") -> str:
        """根据语言获取商品名称."""
        return getattr(self, f"name_{lang}", self.name_zh)

    def get_description(self, lang: str = "zh") -> str | None:
        """根据语言获取商品描述."""
        return getattr(self, f"description_{lang}", self.description_zh)


class ProductVariant(Base):
    """商品规格与自动回复表."""

    __tablename__ = "product_variants"

    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(128), nullable=False)
    auto_reply_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_reply_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_reply_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[str | None] = mapped_column(nullable=True)

    # 关系
    product: Mapped[Product] = relationship("Product", back_populates="variants")

    __table_args__ = (
        Index("uq_product_variant", "product_id", "variant_key", unique=True),
    )

    def get_name(self, lang: str = "zh") -> str:
        """根据语言获取规格名称."""
        return getattr(self, f"name_{lang}", self.name_zh)

    def get_auto_reply(self, lang: str = "zh") -> str | None:
        """根据语言获取自动回复内容."""
        return getattr(self, f"auto_reply_{lang}", self.auto_reply_zh)

    @property
    def has_auto_reply(self) -> bool:
        """是否有预设自动回复."""
        return bool(self.auto_reply_zh)
