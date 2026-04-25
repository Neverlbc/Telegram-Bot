"""莫斯科现货查询 — 公开 / VIP 两级库存视图.

普通查询：读取 Outdoor 表，仅展示 is_public=True 的行。
VIP 查询：输入密码 → 读取完整 Outdoor 表。
无货：公开查询联系客服，VIP 查询标记空运需求。
"""

from __future__ import annotations

import logging
from html import escape
from unicodedata import east_asian_width

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import InventoryCallback, NavCallback
from bot.keyboards.inline import inventory_category_keyboard, inventory_menu_keyboard
from bot.services.outdoor_sheets import OutdoorItem, get_outdoor_inventory

logger = logging.getLogger(__name__)
router = Router(name="inventory")

# ── 多语言文案 ──────────────────────────────────────────

TEXTS: dict[str, dict[str, str]] = {
    "zh": {
        "menu_title": "🔍 <b>莫斯科现货查询</b>\n\n请选择查询方式：",
        "category_title": "📂 请选择品类：",
        "brand_title": "🏷 <b>请选择品牌</b>\n\n点击品牌查看对应库存：",
        "quick_title_public": "⚡ <b>快速展示 · 当前有货</b>（公开库存）\n\n",
        "quick_title_vip": "⚡ <b>快速展示 · 当前有货</b>（VIP 完整库存）\n\n",
        "quick_empty_public": "📭 当前公开库存暂无有货商品。\n\n如需进一步了解，请联系客服：",
        "quick_empty_vip": "📭 当前 VIP 库存暂无有货商品。\n\n如需预约空运，请联系：",
        "stock_title_public": "📦 <b>莫斯科 · 户外类现货</b>\n\n",
        "stock_title_vip": "⭐ <b>莫斯科 · 户外类现货</b>\n\n",
        "no_stock_public": "❌ 当前暂无公开库存。\n\n如需进一步了解，请联系客服：",
        "no_stock_vip": "❌ 当前暂无库存（含空运预约）。\n\n如需预约空运，请联系：",
        "contact_tg": "💬 TG 联系客服",
        "contact_wa": "💬 WhatsApp 联系",
        "data_delay": "\n\n<i>数据可能有 5 分钟缓存延迟</i>",
        "loading_err": "❌ 读取库存失败，请稍后重试。",
        "not_configured": "⚠️ 库存服务暂未配置，请稍后再试。",
    },
    "en": {
        "menu_title": "🔍 <b>Moscow Inventory Query</b>\n\nSelect query type:",
        "category_title": "📂 Select category:",
        "brand_title": "🏷 <b>Select a brand</b>\n\nTap a brand to view inventory:",
        "quick_title_public": "⚡ <b>Quick View · In Stock</b> (Public)\n\n",
        "quick_title_vip": "⚡ <b>Quick View · In Stock</b> (VIP Full View)\n\n",
        "quick_empty_public": "📭 No in-stock public items at the moment.\n\nContact support:",
        "quick_empty_vip": "📭 No in-stock VIP items at the moment.\n\nTo book air freight:",
        "stock_title_public": "📦 <b>Moscow · Outdoor Stock</b>\n\n",
        "stock_title_vip": "⭐ <b>Moscow · Outdoor Stock</b>\n\n",
        "no_stock_public": "❌ No public inventory available.\n\nContact support:",
        "no_stock_vip": "❌ No inventory available (incl. air freight).\n\nTo book air freight:",
        "contact_tg": "💬 TG Contact",
        "contact_wa": "💬 WhatsApp",
        "data_delay": "\n\n<i>Data may be up to 5 minutes delayed</i>",
        "loading_err": "❌ Failed to load inventory. Please try again.",
        "not_configured": "⚠️ Inventory service not configured yet.",
    },
    "ru": {
        "menu_title": "🔍 <b>Наличие в Москве</b>\n\nВыберите тип запроса:",
        "category_title": "📂 Выберите категорию:",
        "brand_title": "🏷 <b>Выберите бренд</b>\n\nНажмите бренд, чтобы посмотреть наличие:",
        "quick_title_public": "⚡ <b>Быстрый просмотр · В наличии</b> (общий)\n\n",
        "quick_title_vip": "⚡ <b>Быстрый просмотр · В наличии</b> (VIP полный список)\n\n",
        "quick_empty_public": "📭 Сейчас нет товаров в наличии в публичном списке.\n\nСвяжитесь с поддержкой:",
        "quick_empty_vip": "📭 Сейчас нет товаров в наличии в VIP списке.\n\nДля заказа авиадоставки:",
        "stock_title_public": "📦 <b>Москва · Аутдор — наличие</b>\n\n",
        "stock_title_vip": "⭐ <b>Москва · Аутдор — наличие</b>\n\n",
        "no_stock_public": "❌ Публичный список пуст.\n\nСвяжитесь с поддержкой:",
        "no_stock_vip": "❌ Нет в наличии (включая авиа).\n\nДля заказа авиадоставки:",
        "contact_tg": "💬 TG Связаться",
        "contact_wa": "💬 WhatsApp",
        "data_delay": "\n\n<i>Данные обновляются раз в 5 минут</i>",
        "loading_err": "❌ Ошибка загрузки. Попробуйте позже.",
        "not_configured": "⚠️ Сервис наличия ещё не настроен.",
    },
}


def _t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"][key])


# ── 表格格式化（复用 presale.py 逻辑，适配 OutdoorItem）──

def _display_width(value: str) -> int:
    return sum(2 if east_asian_width(char) in {"F", "W"} else 1 for char in value)


def _fit_cell(value: str, width: int) -> str:
    return value + " " * max(0, width - _display_width(value))


def _right_cell(value: str, width: int) -> str:
    return " " * max(0, width - _display_width(value)) + value


def _wrap_cell(value: str, width: int) -> list[str]:
    if not value:
        return [""]
    lines: list[str] = []
    current, current_w = "", 0
    for char in value:
        cw = 2 if east_asian_width(char) in {"F", "W"} else 1
        if current and current_w + cw > width:
            lines.append(current)
            current, current_w = char, cw
        else:
            current += char
            current_w += cw
    if current:
        lines.append(current)
    return lines


def _format_outdoor_table(items: list[OutdoorItem], lang: str) -> str:
    """生成按品牌分组的户外库存表格 HTML（<pre> 包裹）."""
    if not items:
        return ""

    hdr = {
        "zh": ("SKU", "QTYS", "状态", "备注"),
        "en": ("SKU", "QTYS", "Status", "Notes"),
        "ru": ("SKU", "QTYS", "Статус", "Примеч."),
    }.get(lang, ("SKU", "QTYS", "状态", "备注"))

    names = [i.sku for i in items]
    qtys = [str(i.qty) for i in items]
    statuses = [i.status_text(lang) for i in items]
    notes = [i.notes or "-" for i in items]

    name_w = max(_display_width(hdr[0]), min(max(_display_width(n) for n in names), 15))
    qty_w = max(_display_width(hdr[1]), max(_display_width(q) for q in qtys))
    status_w = max(_display_width(hdr[2]), max(_display_width(s) for s in statuses))
    notes_w = max(_display_width(hdr[3]), min(max(_display_width(n) for n in notes), 8))

    header = (
        f"{_fit_cell(hdr[0], name_w)} "
        f"{_right_cell(hdr[1], qty_w)} "
        f"{_fit_cell(hdr[2], status_w)} "
        f"{_fit_cell(hdr[3], notes_w)}"
    )
    sep = "\u2500" * 20
    other_brand = {"zh": "其他", "en": "Other", "ru": "Другое"}.get(lang, "其他")

    rows: list[str] = []
    current_brand: str | None = None
    for idx, item in enumerate(items):
        brand = item.brand or other_brand
        if brand != current_brand:
            if rows:
                rows.append("")
            rows.append(f"【{brand}】")
            rows.append(header)
            rows.append(sep)
            current_brand = brand

        name_lines = _wrap_cell(item.sku, name_w)
        qty_lines = _wrap_cell(str(item.qty), qty_w)
        status_lines = _wrap_cell(item.status_text(lang), status_w)
        note_lines = _wrap_cell(item.notes or "-", notes_w)
        h = max(len(name_lines), len(qty_lines), len(status_lines), len(note_lines))
        for i in range(h):
            nv = name_lines[i] if i < len(name_lines) else ""
            qv = qty_lines[i] if i < len(qty_lines) else ""
            sv = status_lines[i] if i < len(status_lines) else ""
            note = note_lines[i] if i < len(note_lines) else ""
            rows.append(
                f"{_fit_cell(nv, name_w)} "
                f"{_right_cell(qv, qty_w)} "
                f"{_fit_cell(sv, status_w)} "
                f"{_fit_cell(note, notes_w)}"
            )
        if idx < len(items) - 1 and (items[idx + 1].brand or other_brand) == current_brand:
            rows.append(sep)

    table_text = chr(10).join(rows)
    if _display_width(table_text) > 3600:
        table_text = table_text[:3600] + "\n…"
    return f"<pre>{escape(table_text)}</pre>"


def _other_brand_name(lang: str = "zh") -> str:
    return {"zh": "其他", "en": "Other", "ru": "Другое"}.get(lang, "其他")


def _ordered_brands(items: list[OutdoorItem], lang: str = "zh") -> list[str]:
    other_brand = _other_brand_name(lang)
    return list(dict.fromkeys((item.brand or other_brand) for item in items))


def _filter_brand_items(items: list[OutdoorItem], brand: str, lang: str = "zh") -> list[OutdoorItem]:
    other_brand = _other_brand_name(lang)
    return [item for item in items if (item.brand or other_brand) == brand]


def _available_items(items: list[OutdoorItem]) -> list[OutdoorItem]:
    return [item for item in items if item.qty > 0]


def _brand_keyboard(items: list[OutdoorItem], lang: str, vip: bool) -> InlineKeyboardBuilder:
    brands = _ordered_brands(items, lang)
    available_count = len(_available_items(items))
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text={
            "zh": f"⚡ 快速展示有货 ({available_count})",
            "en": f"⚡ In-stock Quick View ({available_count})",
            "ru": f"⚡ Быстрый просмотр ({available_count})",
        }.get(lang, f"⚡ 快速展示有货 ({available_count})"),
        callback_data=InventoryCallback(action="quick", cat_id="outdoor", vip=vip).pack(),
    ))
    for idx, brand in enumerate(brands, start=1):
        count = len(_filter_brand_items(items, brand, lang))
        builder.row(InlineKeyboardButton(
            text=f"🏷 {brand} ({count})",
            callback_data=InventoryCallback(action="brand", cat_id="outdoor", vip=vip, page=idx).pack(),
        ))
    builder.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回品类", "en": "◀️ Back", "ru": "◀️ Назад"}.get(lang, "◀️ Back"),
        callback_data=InventoryCallback(action="categories", vip=vip).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 Main Menu"),
        callback_data=NavCallback(action="home").pack(),
    ))
    return builder


def _inventory_whatsapp_url(lang: str, vip: bool, user_id: int | None = None) -> str:
    import urllib.parse

    parsed = urllib.parse.urlparse(settings.inventory_whatsapp_url)
    query = urllib.parse.parse_qs(parsed.query)
    phone = (query.get("phone") or [""])[0]
    if not phone and parsed.netloc.endswith("wa.me"):
        phone = parsed.path.strip("/")

    if not phone:
        return settings.inventory_whatsapp_url

    tag = f"\nTGID:{user_id}" if user_id else ""
    if vip:
        text = {
            "zh": f"你好，我需要了解航空货运服务。{tag}",
            "en": f"Hi, I'd like to ask about air freight service.{tag}",
            "ru": f"Здравствуйте, мне нужно узнать об авиаперевозке грузов.{tag}",
        }.get(lang, f"Hi, air freight inquiry.{tag}")
    else:
        text = {
            "zh": f"你好，我想咨询产品库存和购买信息。{tag}",
            "en": f"Hi, I'd like to ask about product stock and purchase information.{tag}",
            "ru": f"Здравствуйте, хочу узнать о наличии товара и покупке.{tag}",
        }.get(lang, f"Hi, product inquiry.{tag}")

    return f"https://wa.me/{phone}?text={urllib.parse.quote(text)}"


# ── 联系按钮构建（TG + WhatsApp 两个按钮）────────────────

def _contact_buttons(lang: str, vip: bool, user_id: int | None = None) -> list[InlineKeyboardButton]:
    import urllib.parse
    if vip:
        tag = f"请求类型：空运\nTGID:{user_id}" if user_id else "请求类型：空运"
        prefill = {
            "zh": f"自动携带标签\n来源：空运\n{tag}",
            "en": f"Auto tag\nSource: Air freight\n{tag}",
            "ru": f"Автометка\nИсточник: авиадоставка\n{tag}",
        }.get(lang, f"Auto tag\nSource: Air freight\n{tag}")
    else:
        tag = f" (TGID:{user_id})" if user_id else ""
        prefill = {
            "zh": f"你好，我想查询库存{tag}",
            "en": f"Hi, I'd like to check stock{tag}",
            "ru": f"Привет, хочу узнать наличие{tag}",
        }.get(lang, f"Hi, stock inquiry{tag}")
    tg_url = f"https://t.me/{settings.inventory_agent_username}?text={urllib.parse.quote(prefill)}"
    return [
        InlineKeyboardButton(text=_t(lang, "contact_tg"), url=tg_url),
        InlineKeyboardButton(text=_t(lang, "contact_wa"), url=_inventory_whatsapp_url(lang, vip, user_id)),
    ]


# ── Handlers ────────────────────────────────────────────

@router.callback_query(InventoryCallback.filter(F.action == "menu"))
async def on_inventory_menu(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    if state:
        await state.clear()
    await callback.message.edit_text(
        _t(lang, "menu_title"),
        reply_markup=inventory_menu_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "public_query"))
async def on_public_query(callback: CallbackQuery, lang: str = "zh") -> None:
    if not callback.message:
        return
    await callback.message.edit_text(
        _t(lang, "category_title"),
        reply_markup=inventory_category_keyboard(lang, vip=False),
    )
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "categories"))
async def on_inventory_categories(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
) -> None:
    if not callback.message:
        return
    await callback.message.edit_text(
        _t(lang, "category_title"),
        reply_markup=inventory_category_keyboard(lang, vip=callback_data.vip),
    )
    await callback.answer()


@router.message(StateFilter(default_state), F.text == settings.vip_inventory_password)
async def on_vip_password_text(message: Message, lang: str = "zh") -> None:
    """VIP 密码文本触发（无按钮，直接发密码即可进入 VIP 查询）."""
    await message.answer(
        _t(lang, "category_title"),
        reply_markup=inventory_category_keyboard(lang, vip=True),
    )


@router.callback_query(InventoryCallback.filter(F.action == "category"))
async def on_inventory_category(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
) -> None:
    """品类选择后展示品牌列表."""
    if not callback.message:
        return

    vip = callback_data.vip
    cat_id = callback_data.cat_id

    if cat_id != "outdoor":
        await callback.answer("Coming soon", show_alert=True)
        return

    if not settings.outdoor_sheet_id:
        await callback.message.edit_text(_t(lang, "not_configured"))
        await callback.answer()
        return

    try:
        items = await get_outdoor_inventory(vip=vip)
    except Exception as e:
        logger.error("get_outdoor_inventory failed: %s", e)
        await callback.message.edit_text(_t(lang, "loading_err"))
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()

    if not items:
        user_id = callback.from_user.id if callback.from_user else None
        builder.row(*_contact_buttons(lang, vip, user_id))
        builder.row(InlineKeyboardButton(
            text={"zh": "◀️ 返回", "en": "◀️ Back", "ru": "◀️ Назад"}.get(lang, "◀️ Back"),
            callback_data=InventoryCallback(action="menu").pack(),
        ))
        builder.row(InlineKeyboardButton(
            text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 Main Menu"),
            callback_data=NavCallback(action="home").pack(),
        ))
        no_stock_key = "no_stock_vip" if vip else "no_stock_public"
        await callback.message.edit_text(
            _t(lang, no_stock_key),
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        _t(lang, "brand_title"),
        reply_markup=_brand_keyboard(items, lang, vip).as_markup(),
    )
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "brand"))
async def on_inventory_brand(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
) -> None:
    """品牌选择后展示该品牌库存."""
    if not callback.message:
        return

    vip = callback_data.vip

    if not settings.outdoor_sheet_id:
        await callback.message.edit_text(_t(lang, "not_configured"))
        await callback.answer()
        return

    try:
        items = await get_outdoor_inventory(vip=vip)
    except Exception as e:
        logger.error("get_outdoor_inventory failed: %s", e)
        await callback.message.edit_text(_t(lang, "loading_err"))
        await callback.answer()
        return

    brands = _ordered_brands(items, lang)
    brand_idx = callback_data.page - 1
    if brand_idx < 0 or brand_idx >= len(brands):
        await callback.answer(_t(lang, "loading_err"), show_alert=True)
        return

    brand = brands[brand_idx]
    brand_items = _filter_brand_items(items, brand, lang)
    builder = InlineKeyboardBuilder()

    if not brand_items:
        await callback.answer(_t(lang, "loading_err"), show_alert=True)
        return

    table_html = _format_outdoor_table(brand_items, lang)
    title_key = "stock_title_vip" if vip else "stock_title_public"
    text = _t(lang, title_key) + table_html + _t(lang, "data_delay")

    user_id = callback.from_user.id if callback.from_user else None
    builder.row(*_contact_buttons(lang, vip, user_id))
    builder.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回品牌", "en": "◀️ Brands", "ru": "◀️ Бренды"}.get(lang, "◀️ Brands"),
        callback_data=InventoryCallback(action="category", cat_id="outdoor", vip=vip).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 Main Menu"),
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "quick"))
async def on_inventory_quick(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
) -> None:
    """快速展示所有品牌中当前有货的库存."""
    if not callback.message:
        return

    vip = callback_data.vip

    if not settings.outdoor_sheet_id:
        await callback.message.edit_text(_t(lang, "not_configured"))
        await callback.answer()
        return

    try:
        items = await get_outdoor_inventory(vip=vip)
    except Exception as e:
        logger.error("get_outdoor_inventory failed: %s", e)
        await callback.message.edit_text(_t(lang, "loading_err"))
        await callback.answer()
        return

    available_items = _available_items(items)
    builder = InlineKeyboardBuilder()
    user_id = callback.from_user.id if callback.from_user else None

    if not available_items:
        builder.row(*_contact_buttons(lang, vip, user_id))
        builder.row(InlineKeyboardButton(
            text={"zh": "◀️ 返回品牌", "en": "◀️ Brands", "ru": "◀️ Бренды"}.get(lang, "◀️ Brands"),
            callback_data=InventoryCallback(action="category", cat_id="outdoor", vip=vip).pack(),
        ))
        builder.row(InlineKeyboardButton(
            text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 Main Menu"),
            callback_data=NavCallback(action="home").pack(),
        ))
        empty_key = "quick_empty_vip" if vip else "quick_empty_public"
        await callback.message.edit_text(_t(lang, empty_key), reply_markup=builder.as_markup())
        await callback.answer()
        return

    title_key = "quick_title_vip" if vip else "quick_title_public"
    table_html = _format_outdoor_table(available_items, lang)
    text = _t(lang, title_key) + table_html + _t(lang, "data_delay")

    builder.row(*_contact_buttons(lang, vip, user_id))
    builder.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回品牌", "en": "◀️ Brands", "ru": "◀️ Бренды"}.get(lang, "◀️ Brands"),
        callback_data=InventoryCallback(action="category", cat_id="outdoor", vip=vip).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 Main Menu"),
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()
