"""售前咨询 — 商品清单 / 配送说明 / 常见问题.

M3 完整实现：
- 商品类目浏览 (Category -> Product -> Variant -> 自动回复)
- FAQ 列表与详情
- 配送说明列表与详情
"""

from __future__ import annotations

import logging
import math

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.callbacks import NavCallback, PresaleCallback
from bot.services.catalog import (
    get_category_by_id,
    get_product_by_id,
    get_products_by_category,
    get_subcategories,
    get_top_categories,
)
from bot.services.faq_service import get_delivery_list, get_faq_item_by_id, get_faq_list

logger = logging.getLogger(__name__)
router = Router(name="presale")

PAGE_SIZE = 8  # 每页商品数量


# ── 多语言文案 ──────────────────────────────────────────

TEXTS = {
    "zh": {
        "catalog_title": "📋 <b>商品分类</b>\n\n请选择一个分类查看商品：",
        "subcategory_title": "📂 <b>{name}</b>\n\n请选择子分类：",
        "products_title": "🛍 <b>{name}</b>\n\n请选择商品（第 {page}/{total_pages} 页）：",
        "products_empty": "📭 该分类暂无商品。",
        "product_detail": (
            "📦 <b>{name}</b>\n\n"
            "{description}\n\n"
            "请选择规格了解详情："
        ),
        "product_no_desc": "暂无描述",
        "variant_detail": (
            "🔖 <b>{product_name}</b> — {variant_name}\n\n"
            "{auto_reply}"
        ),
        "variant_no_reply": "暂无自动回复内容，请联系客服获取信息。",
        "faq_title": "❓ <b>常见问题</b>\n\n请选择问题查看答案：",
        "faq_empty": "📭 暂无常见问题。",
        "faq_detail": "❓ <b>{question}</b>\n\n{answer}",
        "delivery_title": "🚚 <b>配送说明</b>\n\n请选择查看详情：",
        "delivery_empty": "📭 暂无配送说明。",
        "delivery_detail": "🚚 <b>{question}</b>\n\n{answer}",
        "no_db": "⚠️ 数据库未连接，暂时无法查看。",
        "prev": "◀️ 上一页",
        "next": "下一页 ▶️",
        "contact_cs": "💬 联系客服",
    },
    "en": {
        "catalog_title": "📋 <b>Product Categories</b>\n\nSelect a category:",
        "subcategory_title": "📂 <b>{name}</b>\n\nSelect a subcategory:",
        "products_title": "🛍 <b>{name}</b>\n\nSelect a product (Page {page}/{total_pages}):",
        "products_empty": "📭 No products in this category yet.",
        "product_detail": (
            "📦 <b>{name}</b>\n\n"
            "{description}\n\n"
            "Select a variant for details:"
        ),
        "product_no_desc": "No description available",
        "variant_detail": (
            "🔖 <b>{product_name}</b> — {variant_name}\n\n"
            "{auto_reply}"
        ),
        "variant_no_reply": "No info available. Please contact support.",
        "faq_title": "❓ <b>FAQ</b>\n\nSelect a question:",
        "faq_empty": "📭 No FAQ entries yet.",
        "faq_detail": "❓ <b>{question}</b>\n\n{answer}",
        "delivery_title": "🚚 <b>Delivery Info</b>\n\nSelect for details:",
        "delivery_empty": "📭 No delivery info yet.",
        "delivery_detail": "🚚 <b>{question}</b>\n\n{answer}",
        "no_db": "⚠️ Database unavailable.",
        "prev": "◀️ Prev",
        "next": "Next ▶️",
        "contact_cs": "💬 Contact Support",
    },
    "ru": {
        "catalog_title": "📋 <b>Категории</b>\n\nВыберите категорию:",
        "subcategory_title": "📂 <b>{name}</b>\n\nВыберите подкатегорию:",
        "products_title": "🛍 <b>{name}</b>\n\nВыберите товар (стр. {page}/{total_pages}):",
        "products_empty": "📭 Нет товаров в этой категории.",
        "product_detail": (
            "📦 <b>{name}</b>\n\n"
            "{description}\n\n"
            "Выберите вариант:"
        ),
        "product_no_desc": "Описание отсутствует",
        "variant_detail": (
            "🔖 <b>{product_name}</b> — {variant_name}\n\n"
            "{auto_reply}"
        ),
        "variant_no_reply": "Информация недоступна. Обратитесь в поддержку.",
        "faq_title": "❓ <b>FAQ</b>\n\nВыберите вопрос:",
        "faq_empty": "📭 FAQ пока нет.",
        "faq_detail": "❓ <b>{question}</b>\n\n{answer}",
        "delivery_title": "🚚 <b>Доставка</b>\n\nВыберите для подробностей:",
        "delivery_empty": "📭 Информации о доставке пока нет.",
        "delivery_detail": "🚚 <b>{question}</b>\n\n{answer}",
        "no_db": "⚠️ БД недоступна.",
        "prev": "◀️ Назад",
        "next": "Далее ▶️",
        "contact_cs": "💬 Поддержка",
    },
}


def t(lang: str, key: str) -> str:
    """获取多语言文案."""
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"][key])


def _nav_buttons(back_target: str) -> list[list[InlineKeyboardButton]]:
    """导航按钮行."""
    back_texts = {"presale": "◀️", "menu": "🏠"}
    return [
        [InlineKeyboardButton(
            text="◀️ 返回上级",
            callback_data=NavCallback(action="back", target=back_target).pack(),
        )],
        [InlineKeyboardButton(
            text="🏠 主菜单",
            callback_data=NavCallback(action="home").pack(),
        )],
    ]


# ── 商品分类入口 ────────────────────────────────────────

@router.callback_query(PresaleCallback.filter())
async def on_presale_action(
    callback: CallbackQuery,
    callback_data: PresaleCallback,
    lang: str = "zh",
    session: AsyncSession | None = None,
) -> None:
    """统一处理售前咨询所有回调."""
    if not callback.message:
        return

    # 无数据库连接时的降级处理
    if session is None:
        await callback.message.edit_text(t(lang, "no_db"))
        await callback.answer()
        return

    action = callback_data.action

    if action == "catalog":
        await _show_catalog(callback, lang, session)
    elif action == "category":
        await _show_category(callback, callback_data, lang, session)
    elif action == "product":
        await _show_product(callback, callback_data, lang, session)
    elif action == "variant":
        await _show_variant(callback, callback_data, lang, session)
    elif action == "faq":
        await _show_faq_list(callback, lang, session)
    elif action == "faq_detail":
        await _show_faq_detail(callback, callback_data, lang, session)
    elif action == "delivery":
        await _show_delivery_list(callback, lang, session)
    elif action == "delivery_detail":
        await _show_delivery_detail(callback, callback_data, lang, session)
    else:
        await callback.answer()
        return

    await callback.answer()


# ── 商品目录浏览 ────────────────────────────────────────

async def _show_catalog(
    callback: CallbackQuery, lang: str, session: AsyncSession,
) -> None:
    """展示顶级分类列表."""
    categories = await get_top_categories(session)

    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(
            text=f"📂 {cat.get_name(lang)}",
            callback_data=PresaleCallback(action="category", category_id=cat.id).pack(),
        ))
    for row in _nav_buttons("presale"):
        builder.row(*row)

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "catalog_title"),
        reply_markup=builder.as_markup(),
    )


async def _show_category(
    callback: CallbackQuery,
    data: PresaleCallback,
    lang: str,
    session: AsyncSession,
) -> None:
    """展示子分类或商品列表."""
    category_id = data.category_id
    page = data.page

    category = await get_category_by_id(session, category_id)
    if not category:
        await callback.answer("❌ Category not found", show_alert=True)
        return

    # 先检查是否有子分类
    subcategories = await get_subcategories(session, category_id)
    if subcategories:
        builder = InlineKeyboardBuilder()
        for sub in subcategories:
            builder.row(InlineKeyboardButton(
                text=f"📂 {sub.get_name(lang)}",
                callback_data=PresaleCallback(action="category", category_id=sub.id).pack(),
            ))
        # 返回上一级（如果有父级就返回父级分类，否则返回目录首页）
        if category.parent_id:
            builder.row(InlineKeyboardButton(
                text="◀️ 返回上级",
                callback_data=PresaleCallback(action="category", category_id=category.parent_id).pack(),
            ))
        else:
            builder.row(InlineKeyboardButton(
                text="◀️ 返回分类",
                callback_data=PresaleCallback(action="catalog").pack(),
            ))
        builder.row(InlineKeyboardButton(
            text="🏠 主菜单",
            callback_data=NavCallback(action="home").pack(),
        ))

        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "subcategory_title").format(name=category.get_name(lang)),
            reply_markup=builder.as_markup(),
        )
        return

    # 没有子分类 → 展示商品列表
    products, total = await get_products_by_category(session, category_id, page, PAGE_SIZE)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    if not products:
        builder = InlineKeyboardBuilder()
        if category.parent_id:
            builder.row(InlineKeyboardButton(
                text="◀️ 返回上级",
                callback_data=PresaleCallback(action="category", category_id=category.parent_id).pack(),
            ))
        else:
            builder.row(InlineKeyboardButton(
                text="◀️ 返回分类",
                callback_data=PresaleCallback(action="catalog").pack(),
            ))
        builder.row(InlineKeyboardButton(
            text="🏠 主菜单",
            callback_data=NavCallback(action="home").pack(),
        ))
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "products_empty"),
            reply_markup=builder.as_markup(),
        )
        return

    builder = InlineKeyboardBuilder()
    for prod in products:
        builder.row(InlineKeyboardButton(
            text=f"📦 {prod.get_name(lang)}",
            callback_data=PresaleCallback(
                action="product", product_id=prod.id, category_id=category_id,
            ).pack(),
        ))

    # 翻页按钮
    pagination_row: list[InlineKeyboardButton] = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(
            text=t(lang, "prev"),
            callback_data=PresaleCallback(
                action="category", category_id=category_id, page=page - 1,
            ).pack(),
        ))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(
            text=t(lang, "next"),
            callback_data=PresaleCallback(
                action="category", category_id=category_id, page=page + 1,
            ).pack(),
        ))
    if pagination_row:
        builder.row(*pagination_row)

    # 返回导航
    if category.parent_id:
        builder.row(InlineKeyboardButton(
            text="◀️ 返回上级",
            callback_data=PresaleCallback(action="category", category_id=category.parent_id).pack(),
        ))
    else:
        builder.row(InlineKeyboardButton(
            text="◀️ 返回分类",
            callback_data=PresaleCallback(action="catalog").pack(),
        ))
    builder.row(InlineKeyboardButton(
        text="🏠 主菜单",
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "products_title").format(
            name=category.get_name(lang), page=page, total_pages=total_pages,
        ),
        reply_markup=builder.as_markup(),
    )


async def _show_product(
    callback: CallbackQuery,
    data: PresaleCallback,
    lang: str,
    session: AsyncSession,
) -> None:
    """展示商品详情及其规格列表."""
    product = await get_product_by_id(session, data.product_id)
    if not product:
        await callback.answer("❌ Product not found", show_alert=True)
        return

    description = product.get_description(lang) or t(lang, "product_no_desc")
    builder = InlineKeyboardBuilder()

    # 规格列表
    active_variants = [v for v in product.variants if v.is_active]
    for var in sorted(active_variants, key=lambda v: v.sort_order):
        builder.row(InlineKeyboardButton(
            text=f"🔖 {var.get_name(lang)}",
            callback_data=PresaleCallback(
                action="variant",
                product_id=product.id,
                category_id=data.category_id,
                variant=str(var.id),
            ).pack(),
        ))

    # 联系客服快捷按钮
    from bot.keyboards.callbacks import SupportCallback
    builder.row(InlineKeyboardButton(
        text=t(lang, "contact_cs"),
        callback_data=SupportCallback(action="human").pack(),
    ))

    # 返回该分类的商品列表
    builder.row(InlineKeyboardButton(
        text="◀️ 返回商品列表",
        callback_data=PresaleCallback(action="category", category_id=data.category_id).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="🏠 主菜单",
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "product_detail").format(name=product.get_name(lang), description=description),
        reply_markup=builder.as_markup(),
    )


async def _show_variant(
    callback: CallbackQuery,
    data: PresaleCallback,
    lang: str,
    session: AsyncSession,
) -> None:
    """展示规格详情及自动回复内容."""
    from bot.services.catalog import get_variant_by_id

    variant_id = int(data.variant) if data.variant else 0
    variant = await get_variant_by_id(session, variant_id)
    if not variant:
        await callback.answer("❌ Variant not found", show_alert=True)
        return

    product = await get_product_by_id(session, data.product_id)
    product_name = product.get_name(lang) if product else "—"

    auto_reply = variant.get_auto_reply(lang) or t(lang, "variant_no_reply")
    builder = InlineKeyboardBuilder()

    # 联系客服
    from bot.keyboards.callbacks import SupportCallback
    builder.row(InlineKeyboardButton(
        text=t(lang, "contact_cs"),
        callback_data=SupportCallback(action="human").pack(),
    ))

    # 返回商品详情
    builder.row(InlineKeyboardButton(
        text="◀️ 返回商品",
        callback_data=PresaleCallback(
            action="product", product_id=data.product_id, category_id=data.category_id,
        ).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="🏠 主菜单",
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "variant_detail").format(
            product_name=product_name,
            variant_name=variant.get_name(lang),
            auto_reply=auto_reply,
        ),
        reply_markup=builder.as_markup(),
    )


# ── FAQ ─────────────────────────────────────────────────

async def _show_faq_list(
    callback: CallbackQuery, lang: str, session: AsyncSession,
) -> None:
    """展示 FAQ 列表."""
    items = await get_faq_list(session)

    builder = InlineKeyboardBuilder()
    if not items:
        for row in _nav_buttons("presale"):
            builder.row(*row)
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "faq_empty"),
            reply_markup=builder.as_markup(),
        )
        return

    for item in items:
        q = item.get_question(lang) or f"FAQ #{item.id}"
        builder.row(InlineKeyboardButton(
            text=f"❓ {q}",
            callback_data=PresaleCallback(action="faq_detail", faq_id=item.id).pack(),
        ))
    for row in _nav_buttons("presale"):
        builder.row(*row)

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "faq_title"),
        reply_markup=builder.as_markup(),
    )


async def _show_faq_detail(
    callback: CallbackQuery,
    data: PresaleCallback,
    lang: str,
    session: AsyncSession,
) -> None:
    """展示 FAQ 详情."""
    item = await get_faq_item_by_id(session, data.faq_id)
    if not item:
        await callback.answer("❌ FAQ not found", show_alert=True)
        return

    question = item.get_question(lang) or f"FAQ #{item.id}"
    answer = item.get_answer(lang)
    template_key = "faq_detail"

    builder = InlineKeyboardBuilder()
    # 返回 FAQ 列表
    builder.row(InlineKeyboardButton(
        text="◀️ 返回列表",
        callback_data=PresaleCallback(action="faq").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="🏠 主菜单",
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, template_key).format(question=question, answer=answer),
        reply_markup=builder.as_markup(),
    )


# ── 配送说明 ────────────────────────────────────────────

async def _show_delivery_list(
    callback: CallbackQuery, lang: str, session: AsyncSession,
) -> None:
    """展示配送说明列表."""
    items = await get_delivery_list(session)

    builder = InlineKeyboardBuilder()
    if not items:
        for row in _nav_buttons("presale"):
            builder.row(*row)
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "delivery_empty"),
            reply_markup=builder.as_markup(),
        )
        return

    for item in items:
        q = item.get_question(lang) or f"Delivery #{item.id}"
        builder.row(InlineKeyboardButton(
            text=f"🚚 {q}",
            callback_data=PresaleCallback(action="delivery_detail", faq_id=item.id).pack(),
        ))
    for row in _nav_buttons("presale"):
        builder.row(*row)

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "delivery_title"),
        reply_markup=builder.as_markup(),
    )


async def _show_delivery_detail(
    callback: CallbackQuery,
    data: PresaleCallback,
    lang: str,
    session: AsyncSession,
) -> None:
    """展示配送说明详情."""
    item = await get_faq_item_by_id(session, data.faq_id)
    if not item:
        await callback.answer("❌ Not found", show_alert=True)
        return

    question = item.get_question(lang) or f"Delivery #{item.id}"
    answer = item.get_answer(lang)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="◀️ 返回列表",
        callback_data=PresaleCallback(action="delivery").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="🏠 主菜单",
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "delivery_detail").format(question=question, answer=answer),
        reply_markup=builder.as_markup(),
    )
