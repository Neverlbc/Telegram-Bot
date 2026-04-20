"""售前咨询 — 商品清单 / 配送说明 / 常见问题.

M3 完整实现：
- 商品类目浏览 (顶级分类 -> 子分类)
- 实时库存查询 (对接 Google Sheets)
- FAQ 列表与详情
- 配送说明列表与详情
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from html import escape
from unicodedata import east_asian_width

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.callbacks import NavCallback, PresaleCallback
from bot.services.faq_service import get_delivery_list, get_faq_item_by_id, get_faq_list
from bot.services.sheets import (
    SHEET_CONFIG,
    TOP_CATEGORIES,
    InventoryItem,
    get_category_name,
    get_inventory,
    get_sheet_name,
)

logger = logging.getLogger(__name__)
router = Router(name="presale")


# ── 多语言文案 ──────────────────────────────────────────

TEXTS = {
    "zh": {
        "catalog_title": "📋 <b>商品分类</b>\n\n请选择一个分类查看商品：",
        "subcategory_title": "📂 <b>{name}</b>\n\n请选择子分类：",
        "inventory_title": "🛍 <b>{name} 实时库存</b>\n\n当前可下单数量如下：\n\n{inventory_list}\n\n<i>(数据可能存在5分钟延迟)</i>",
        "inventory_empty": "📭 <b>{name}</b> 暂无可用库存。",
        "inventory_more": "… 其余 {count} 条库存未显示",
        "faq_title": "❓ <b>常见问题</b>\n\n请选择问题查看答案：",
        "faq_empty": "📭 暂无常见问题。",
        "faq_detail": "❓ <b>{question}</b>\n\n{answer}",
        "delivery_title": "🚚 <b>配送说明</b>\n\n请选择查看详情：",
        "delivery_empty": "📭 暂无配送说明。",
        "delivery_detail": "🚚 <b>{question}</b>\n\n{answer}",
        "no_db": "⚠️ 数据库未连接，暂时无法查看。",
        "loading_error": "❌ 拉取库存失败，请稍后再试。",
        "contact_cs": "💬 联系客服",
    },
    "en": {
        "catalog_title": "📋 <b>Product Categories</b>\n\nSelect a category:",
        "subcategory_title": "📂 <b>{name}</b>\n\nSelect a subcategory:",
        "inventory_title": "🛍 <b>{name} Live Inventory</b>\n\nAvailable to order:\n\n{inventory_list}\n\n<i>(Data may be up to 5 mins delayed)</i>",
        "inventory_empty": "📭 No stock available for <b>{name}</b>.",
        "inventory_more": "… {count} more inventory rows not shown",
        "faq_title": "❓ <b>FAQ</b>\n\nSelect a question:",
        "faq_empty": "📭 No FAQ entries yet.",
        "faq_detail": "❓ <b>{question}</b>\n\n{answer}",
        "delivery_title": "🚚 <b>Delivery Info</b>\n\nSelect for details:",
        "delivery_empty": "📭 No delivery info yet.",
        "delivery_detail": "🚚 <b>{question}</b>\n\n{answer}",
        "no_db": "⚠️ Database unavailable.",
        "loading_error": "❌ Failed to load inventory, please try again later.",
        "contact_cs": "💬 Contact Support",
    },
    "ru": {
        "catalog_title": "📋 <b>Категории</b>\n\nВыберите категорию:",
        "subcategory_title": "📂 <b>{name}</b>\n\nВыберите подкатегорию:",
        "inventory_title": "🛍 <b>{name} Наличие</b>\n\nДоступно для заказа:\n\n{inventory_list}\n\n<i>(Возможна задержка до 5 минут)</i>",
        "inventory_empty": "📭 Нет товаров в наличии для <b>{name}</b>.",
        "inventory_more": "… ещё {count} строк не показано",
        "faq_title": "❓ <b>FAQ</b>\n\nВыберите вопрос:",
        "faq_empty": "📭 FAQ пока нет.",
        "faq_detail": "❓ <b>{question}</b>\n\n{answer}",
        "delivery_title": "🚚 <b>Доставка</b>\n\nВыберите для подробностей:",
        "delivery_empty": "📭 Информации о доставке пока нет.",
        "delivery_detail": "🚚 <b>{question}</b>\n\n{answer}",
        "no_db": "⚠️ БД недоступна.",
        "loading_error": "❌ Не удалось загрузить наличие, попробуйте позже.",
        "contact_cs": "💬 Поддержка",
    },
}


def t(lang: str, key: str) -> str:
    """获取多语言文案."""
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"][key])


def _display_width(value: str) -> int:
    """计算字符串在等宽布局中的显示宽度."""
    return sum(2 if east_asian_width(char) in {"F", "W"} else 1 for char in value)


def _fit_table_cell(value: str, width: int) -> str:
    """裁剪并补齐单元格内容."""
    if _display_width(value) <= width:
        return value + " " * (width - _display_width(value))

    result = ""
    current_width = 0
    for char in value:
        char_width = 2 if east_asian_width(char) in {"F", "W"} else 1
        if current_width + char_width > width - 1:
            break
        result += char
        current_width += char_width
    return result + "…" + " " * (width - current_width - 1)


def _right_table_cell(value: str, width: int) -> str:
    """右对齐单元格内容."""
    return " " * max(0, width - _display_width(value)) + value


def _inventory_labels(lang: str) -> dict[str, str]:
    """库存字段标签本地化."""
    labels = {
        "zh": {"sku": "SKU", "qty": "QTYS", "state": "状态", "notes": "备注", "empty": "-"},
        "en": {"sku": "SKU", "qty": "QTYS", "state": "State", "notes": "Notes", "empty": "-"},
        "ru": {"sku": "SKU", "qty": "QTYS", "state": "Статус", "notes": "Примечание", "empty": "-"},
    }
    return labels.get(lang, labels["zh"])


def _compact_state(item: InventoryItem, lang: str) -> str:
    """为窄屏表格生成更紧凑的状态值."""
    state = item.get_display_state(lang)
    compact_map = {
        "zh": {"有货": "有货", "缺货": "缺货", "运输中": "运输中"},
        "en": {"Available": "Avail", "In stock": "Stock", "Out of stock": "OOS", "In transit": "Transit"},
        "ru": {"В наличии": "Есть", "Нет в наличии": "Нет", "В пути": "В пути"},
    }
    return compact_map.get(lang, {}).get(state, state)


def _build_inventory_rows(items: Sequence[InventoryItem], lang: str) -> list[str]:
    """生成适合 Telegram 手机端的紧凑表格."""
    labels = _inventory_labels(lang)

    sku_values = [item.sku for item in items]
    qty_values = [str(item.qty) for item in items]
    state_values = [_compact_state(item, lang) for item in items]
    note_values = [item.get_display_notes(lang) or labels["empty"] for item in items]

    sku_width = max(_display_width(labels["sku"]), min(max(_display_width(value) for value in sku_values), 12))
    qty_width = max(_display_width(labels["qty"]), max(_display_width(value) for value in qty_values))
    state_width = max(_display_width(labels["state"]), min(max(_display_width(value) for value in state_values), 8))
    notes_width = max(_display_width(labels["notes"]), min(max(_display_width(value) for value in note_values), 12))

    lines = [
        (
            f"{_fit_table_cell(labels['sku'], sku_width)}  "
            f"{_right_table_cell(labels['qty'], qty_width)}  "
            f"{_fit_table_cell(labels['state'], state_width)}  "
            f"{_fit_table_cell(labels['notes'], notes_width)}"
        ),
        (
            f"{'─' * sku_width}  "
            f"{'─' * qty_width}  "
            f"{'─' * state_width}  "
            f"{'─' * notes_width}"
        ),
    ]

    for sku_value, qty_value, state_value, note_value in zip(
        sku_values, qty_values, state_values, note_values, strict=False
    ):
        lines.append(
            f"{_fit_table_cell(sku_value, sku_width)}  "
            f"{_right_table_cell(qty_value, qty_width)}  "
            f"{_fit_table_cell(state_value, state_width)}  "
            f"{_fit_table_cell(note_value, notes_width)}"
        )

    return lines


def _format_inventory_list(items: Sequence[InventoryItem], lang: str, max_length: int = 3200) -> str:
    """将库存列表格式化为适合 Telegram 手机端展示的紧凑表格."""
    shown_count = len(items)

    while shown_count > 0:
        shown_items = items[:shown_count]
        table_lines = _build_inventory_rows(shown_items, lang)
        inventory_html = f"<pre>{escape(chr(10).join(table_lines))}</pre>"

        more_html = ""
        if shown_count < len(items):
            more_html = "\n\n" + t(lang, "inventory_more").format(count=len(items) - shown_count)

        full_html = inventory_html + more_html
        if len(full_html) <= max_length:
            return full_html

        shown_count -= 1

    table_lines = _build_inventory_rows(items[:1], lang)
    return f"<pre>{escape(chr(10).join(table_lines))}</pre>"


def _nav_buttons(back_target: str) -> list[list[InlineKeyboardButton]]:
    """导航按钮行."""
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

    # FAQ 确实需要 DB 连接，库存查询不需要（但以防万一直接检查）
    if session is None and callback_data.action in ("faq", "faq_detail", "delivery", "delivery_detail"):
        await callback.message.edit_text(t(lang, "no_db"))
        await callback.answer()
        return

    action = callback_data.action

    if action == "catalog":
        await _show_catalog(callback, lang)
    elif action == "category":
        await _show_category(callback, callback_data, lang)
    elif action == "inventory":
        await _show_inventory(callback, callback_data, lang)
    elif action == "faq":
        await _show_faq_list(callback, lang, session)  # type: ignore
    elif action == "faq_detail":
        await _show_faq_detail(callback, callback_data, lang, session)  # type: ignore
    elif action == "delivery":
        await _show_delivery_list(callback, lang, session)  # type: ignore
    elif action == "delivery_detail":
        await _show_delivery_detail(callback, callback_data, lang, session)  # type: ignore
    else:
        await callback.answer()
        return

    await callback.answer()


# ── 商品目录浏览 (对接 Google Sheets) ───────────────────

async def _show_catalog(
    callback: CallbackQuery, lang: str,
) -> None:
    """展示顶级分类列表."""
    builder = InlineKeyboardBuilder()
    for cat_key, cat_data in TOP_CATEGORIES.items():
        name = get_category_name(cat_key, lang)
        
        # 如果是叶子节点（如“动力工具”），直接进入库存查询
        if cat_data.get("leaf"):
            sheet_key = cat_data["children"][0]
            action = "inventory"
            builder.row(InlineKeyboardButton(
                text=f"📂 {name}",
                callback_data=PresaleCallback(action=action, sheet_key=sheet_key, cat_id=cat_key).pack(),
            ))
        else:
            action = "category"
            builder.row(InlineKeyboardButton(
                text=f"📂 {name}",
                callback_data=PresaleCallback(action=action, cat_id=cat_key).pack(),
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
) -> None:
    """展示子分类列表 (如果顶级分类不是叶子节点)."""
    cat_key = data.cat_id
    cat_data = TOP_CATEGORIES.get(cat_key)
    
    if not cat_data:
        await callback.answer("❌ Category not found", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    
    # 罗列子分类 (如 "工业", "狩猎", "特殊")，点击后进入对应库存页
    for sheet_key in cat_data["children"]:
        name = get_sheet_name(sheet_key, lang)
        builder.row(InlineKeyboardButton(
            text=f"📂 {name}",
            callback_data=PresaleCallback(action="inventory", sheet_key=sheet_key, cat_id=cat_key).pack(),
        ))

    builder.row(InlineKeyboardButton(
        text="◀️ 返回分类",
        callback_data=PresaleCallback(action="catalog").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text="🏠 主菜单",
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "subcategory_title").format(name=get_category_name(cat_key, lang)),
        reply_markup=builder.as_markup(),
    )


async def _show_inventory(
    callback: CallbackQuery,
    data: PresaleCallback,
    lang: str,
) -> None:
    """展示从 Google Sheets 查询的库存列表."""
    sheet_key = data.sheet_key
    name = get_sheet_name(sheet_key, lang)
    
    items = await get_inventory(sheet_key)
    builder = InlineKeyboardBuilder()

    # 联系客服
    from bot.keyboards.callbacks import SupportCallback
    builder.row(InlineKeyboardButton(
        text=t(lang, "contact_cs"),
        callback_data=SupportCallback(action="human").pack(),
    ))

    # 返回导航 (如果有父分类就返回，否则返回主目录)
    config = SHEET_CONFIG.get(sheet_key, {})
    parent = config.get("parent")
    
    if parent and not TOP_CATEGORIES.get(parent, {}).get("leaf"):
        builder.row(InlineKeyboardButton(
            text="◀️ 返回上级",
            callback_data=PresaleCallback(action="category", cat_id=parent).pack(),
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

    if not items:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "inventory_empty").format(name=name),
            reply_markup=builder.as_markup(),
        )
        return

    inventory_list = _format_inventory_list(items, lang)
    
    text = t(lang, "inventory_title").format(
        name=name,
        inventory_list=inventory_list,
    )

    if len(text) > 4000:
        text = text[:3900] + "\n\n...(省略多余内容，全部展示已截断)..."

    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
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
