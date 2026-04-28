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
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import InventoryCallback, NavCallback
from bot.keyboards.inline import inventory_category_keyboard, inventory_hidden_menu_keyboard, inventory_menu_keyboard
from bot.services.hidden_access import (
    MENU_SVIP_INVENTORY,
    MENU_VIP_INVENTORY,
    MENU_VVIP_INVENTORY,
    clear_state_keep_hidden_access,
    has_hidden_access,
)
from bot.services.outdoor_sheets import OutdoorItem, get_outdoor_inventory
from bot.services.outdoor_prices import (
    OutdoorPriceItem,
    get_outdoor_price_brand_titles,
    get_outdoor_price_items,
)
from bot.services.inventory_tiers import (
    PRICE_TIER_CODES,
    inventory_price_currency_keys,
    inventory_tier_access_key,
    inventory_tier_label,
    normalize_inventory_tier,
)

logger = logging.getLogger(__name__)
router = Router(name="inventory")

# ── 多语言文案 ──────────────────────────────────────────

TEXTS: dict[str, dict[str, str]] = {
    "zh": {
        "menu_title": (
            "🔍 您好，此模块的主要功能是查询我们莫斯科仓库的产品库存情况（仅包含部分品牌）。\n\n"
            "请选择搜索方式："
        ),
        "category_title": "📂 请选择品类：",
        "tier_category_title": (
            "👁️ 欢迎进入 {tier} 专属隐藏菜单。\n\n"
            "目前为您开放：完整版品牌及现货库存清单。\n\n"
            "库存展示逻辑：\n"
            "莫斯科现货 - 已下单待发货 = 您看到的数字。\n"
            "所见即所得，每一件都是真实可用库存。\n\n"
            "📁 请选择品类："
        ),
        "brand_title": "🏷 <b>请选择品牌</b>\n\n点击品牌查看对应库存：",
        "quick_title_public": "⚡ <b>快速展示 · 当前有货</b>\n\n",
        "quick_title_vip": "⚡ <b>快速展示 · 当前有货</b>\n\n",
        "quick_empty_public": "📭 当前公开库存暂无有货商品。\n\n如需进一步了解，请联系客服：",
        "quick_empty_vip": "📭 当前 VIP 库存暂无有货商品。\n\n如需预约空运，请联系：",
        "stock_title_public": "📦 <b>莫斯科 · 户外类现货</b>\n\n",
        "stock_title_vip": "⭐ <b>莫斯科 · 户外类现货</b>\n\n",
        "no_stock_public": "❌ 当前暂无公开库存。\n\n如需进一步了解，请联系客服：",
        "no_stock_vip": "❌ 当前暂无库存（含空运预约）。\n\n如需预约空运，请联系：",
        "contact_tg": "💬 TG 联系客服",
        "contact_wa": "💬 WhatsApp 联系",
        "data_delay": "\n\n<i>数据可能有 5 分钟缓存延迟</i>",
        "access_expired": "🔐 VIP 访问已过期，请重新输入访问码。",
        "loading_err": "❌ 读取库存失败，请稍后重试。",
        "not_configured": "⚠️ 库存服务暂未配置，请稍后再试。",
    },
    "en": {
        "menu_title": (
            "🔍 Hello, the main function of this module is to check product availability in our Moscow warehouse "
            "(only certain brands are included).\n\n"
            "Please select a search method:"
        ),
        "category_title": "📂 Select category:",
        "tier_category_title": (
            "👁️ Welcome to the {tier} hidden menu.\n\n"
            "Currently unlocked for you: full brand inventory list.\n\n"
            "How stock numbers work:\n"
            "Moscow physical stock - orders awaiting shipment = what you see.\n"
            "What you see is what’s truly available.\n\n"
            "📁 Select category:"
        ),
        "brand_title": "🏷 <b>Select a brand</b>\n\nTap a brand to view inventory:",
        "quick_title_public": "⚡ <b>Quick View · In Stock</b>\n\n",
        "quick_title_vip": "⚡ <b>Quick View · In Stock</b>\n\n",
        "quick_empty_public": "📭 No in-stock public items at the moment.\n\nContact support:",
        "quick_empty_vip": "📭 No in-stock VIP items at the moment.\n\nTo book air freight:",
        "stock_title_public": "📦 <b>Moscow · Outdoor Stock</b>\n\n",
        "stock_title_vip": "⭐ <b>Moscow · Outdoor Stock</b>\n\n",
        "no_stock_public": "❌ No public inventory available.\n\nContact support:",
        "no_stock_vip": "❌ No inventory available (incl. air freight).\n\nTo book air freight:",
        "contact_tg": "💬 TG Contact",
        "contact_wa": "💬 WhatsApp",
        "data_delay": "\n\n<i>Data may be up to 5 minutes delayed</i>",
        "access_expired": "🔐 VIP access has expired. Please enter the access code again.",
        "loading_err": "❌ Failed to load inventory. Please try again.",
        "not_configured": "⚠️ Inventory service not configured yet.",
    },
    "ru": {
        "menu_title": (
            "🔍 Здравствуйте, основная функция этого модуля — проверка наличия товаров на нашем московском складе "
            "(включены только некоторые бренды).\n\n"
            "Пожалуйста, выберите способ поиска:"
        ),
        "category_title": "📂 Выберите категорию:",
        "tier_category_title": (
            "👁️ Добро пожаловать в скрытое меню {tier}.\n\n"
            "Для вас открыт доступ к полному списку брендов и складских остатков в Москве.\n\n"
            "Как формируются остатки:\n"
            "Товар на складе минус уже заказанное, ожидающее отправки = цифра на экране.\n"
            "Всё, что вы видите, — реально доступный товар.\n\n"
            "📁 Выберите категорию:"
        ),
        "brand_title": "🏷 <b>Выберите бренд</b>\n\nНажмите бренд, чтобы посмотреть наличие:",
        "quick_title_public": "⚡ <b>Быстрый просмотр · В наличии</b>\n\n",
        "quick_title_vip": "⚡ <b>Быстрый просмотр · В наличии</b>\n\n",
        "quick_empty_public": "📭 Сейчас нет товаров в наличии в публичном списке.\n\nСвяжитесь с поддержкой:",
        "quick_empty_vip": "📭 Сейчас нет товаров в наличии в VIP списке.\n\nДля заказа авиадоставки:",
        "stock_title_public": "📦 <b>Москва · Аутдор — наличие</b>\n\n",
        "stock_title_vip": "⭐ <b>Москва · Аутдор — наличие</b>\n\n",
        "no_stock_public": "❌ Публичный список пуст.\n\nСвяжитесь с поддержкой:",
        "no_stock_vip": "❌ Нет в наличии (включая авиа).\n\nДля заказа авиадоставки:",
        "contact_tg": "💬 TG Связаться",
        "contact_wa": "💬 WhatsApp",
        "data_delay": "\n\n<i>Данные обновляются раз в 5 минут</i>",
        "access_expired": "🔐 VIP-доступ истёк. Введите код доступа ещё раз.",
        "loading_err": "❌ Ошибка загрузки. Попробуйте позже.",
        "not_configured": "⚠️ Сервис наличия ещё не настроен.",
    },
}

TEXTS["zh"].update({
    "hidden_menu_title": "🔐 欢迎进入 {tier} 专属隐藏菜单。\n\n请选择功能：",
    "price_brand_title": "💰 <b>{tier} 价格查询</b>\n\n请选择品牌。",
    "price_rate_notice": "您好，请注意，当前促销汇率大约为 <b>{rate}</b>",
    "price_rate_notice_no_rate": "您好，请注意，当前促销汇率暂未读取到，请以人工确认为准。",
    "price_title": "",
    "price_selected_brand": "💰 <b>{tier} 价格查询</b>\n品牌：<b>{brand}</b>",
    "price_view_title": "💰 <b>{tier} 价格查询</b>\n品牌：<b>{brand}</b>\n\n请选择展示方式：",
    "price_table_mode": "📋 表格形式",
    "price_image_mode": "🖼 图片形式",
    "price_image_unavailable": "图片形式暂未开放，请先使用表格形式查看。",
    "price_result_header": "表格包含 <b>{count}</b> 个产品信息。",
    "price_done_prompt": "━━━━━━ 已输出完成 ━━━━━━\n您可以继续选择其他品牌查看，或返回主菜单。",
    "price_rate_note": "请注意！当前价格是基于当前的促销汇率【{rate}】进行估算",
    "price_rate_note_no_rate": "请注意！当前促销汇率暂未读取到，请以人工确认为准。",
    "price_image_attached": "见本条消息图片",
    "price_empty": "暂无可展示的价格数据。",
    "price_loading_err": "读取价格表失败，请稍后重试。",
})
TEXTS["en"].update({
    "hidden_menu_title": "🔐 Welcome to the {tier} hidden menu.\n\nPlease choose a function:",
    "price_brand_title": "💰 <b>{tier} Price Query</b>\n\nSelect a brand.",
    "price_rate_notice": "Please note, the current promotional exchange rate is about <b>{rate}</b>.",
    "price_rate_notice_no_rate": (
        "Please note, the promotional exchange rate was not found. Confirm manually before quoting."
    ),
    "price_title": "",
    "price_selected_brand": "💰 <b>{tier} Price Query</b>\nBrand: <b>{brand}</b>",
    "price_view_title": "💰 <b>{tier} Price Query</b>\nBrand: <b>{brand}</b>\n\nChoose a display mode:",
    "price_table_mode": "📋 Table view",
    "price_image_mode": "🖼 Image view",
    "price_image_unavailable": "Image view is not available yet. Please use table view for now.",
    "price_result_header": "This table contains <b>{count}</b> products.",
    "price_done_prompt": (
        "━━━━━━ Finished ━━━━━━\n"
        "You can choose another brand or return to the main menu."
    ),
    "price_rate_note": "Note: this price is estimated using the current promotional exchange rate [{rate}].",
    "price_rate_note_no_rate": "Note: the promotional exchange rate was not found. Confirm manually before quoting.",
    "price_image_attached": "attached to this message",
    "price_empty": "No price data to show.",
    "price_loading_err": "Failed to load the price sheet. Please try again later.",
})
TEXTS["ru"].update({
    "hidden_menu_title": "🔐 Добро пожаловать в скрытое меню {tier}.\n\nВыберите функцию:",
    "price_brand_title": "💰 <b>Цены {tier}</b>\n\nВыберите бренд.",
    "price_rate_notice": "Здравствуйте, обратите внимание: текущий акционный курс примерно <b>{rate}</b>.",
    "price_rate_notice_no_rate": (
        "Здравствуйте, обратите внимание: акционный курс не найден. "
        "Проверьте вручную перед расчётом."
    ),
    "price_title": "",
    "price_selected_brand": "💰 <b>Цены {tier}</b>\nБренд: <b>{brand}</b>",
    "price_view_title": "💰 <b>Цены {tier}</b>\nБренд: <b>{brand}</b>\n\nВыберите формат:",
    "price_table_mode": "📋 Таблица",
    "price_image_mode": "🖼 Изображения",
    "price_image_unavailable": "Формат с изображениями пока недоступен. Используйте таблицу.",
    "price_result_header": "В таблице товаров: <b>{count}</b>.",
    "price_done_prompt": (
        "━━━━━━ Готово ━━━━━━\n"
        "Вы можете выбрать другой бренд или вернуться в главное меню."
    ),
    "price_rate_note": "Внимание! Цена рассчитана по текущему акционному курсу [{rate}].",
    "price_rate_note_no_rate": "Внимание! Акционный курс не найден. Проверьте вручную перед расчётом.",
    "price_image_attached": "прикреплено к этому сообщению",
    "price_empty": "Нет данных по ценам.",
    "price_loading_err": "Не удалось загрузить таблицу цен. Попробуйте позже.",
})


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
    notes = [i.notes_text(lang) for i in items]

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
        note_lines = _wrap_cell(item.notes_text(lang), notes_w)
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


def _stock_first(items: list[OutdoorItem]) -> list[OutdoorItem]:
    return sorted(items, key=lambda item: not item.is_available)


def _available_items(items: list[OutdoorItem]) -> list[OutdoorItem]:
    return _stock_first([item for item in items if item.qty > 0])


def _brand_keyboard(items: list[OutdoorItem], lang: str, vip: bool, tier: str = "") -> InlineKeyboardBuilder:
    brands = _ordered_brands(items, lang)
    available_count = len(_available_items(items))
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text={
            "zh": f"⚡ 快速展示有货 ({available_count})",
            "en": f"⚡ In-stock Quick View ({available_count})",
            "ru": f"⚡ Быстрый просмотр ({available_count})",
        }.get(lang, f"⚡ 快速展示有货 ({available_count})"),
        callback_data=InventoryCallback(action="quick", cat_id="outdoor", vip=vip, tier=tier).pack(),
    ))
    for idx, brand in enumerate(brands, start=1):
        count = len(_filter_brand_items(items, brand, lang))
        builder.row(InlineKeyboardButton(
            text=f"🏷 {brand} ({count})",
            callback_data=InventoryCallback(action="brand", cat_id="outdoor", vip=vip, tier=tier, page=idx).pack(),
        ))
    builder.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回品类", "en": "◀️ Back", "ru": "◀️ Назад"}.get(lang, "◀️ Back"),
        callback_data=InventoryCallback(action="categories", vip=vip, tier=tier).pack(),
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

    if vip:
        text = _vip_airfreight_prefill(user_id)
    else:
        tag = f"\nTGID:{user_id}" if user_id else ""
        text = {
            "zh": f"你好，我想咨询产品库存和购买信息。{tag}",
            "en": f"Hi, I'd like to ask about product stock and purchase information.{tag}",
            "ru": f"Здравствуйте, хочу узнать о наличии товара и покупке.{tag}",
        }.get(lang, f"Hi, product inquiry.{tag}")

    return f"https://wa.me/{phone}?text={urllib.parse.quote(text)}"


def _vip_airfreight_prefill(user_id: int | None = None) -> str:
    tag = f"，TGID:{user_id}" if user_id else ""
    return f"你好，我需要了解航空货运服务。 户外类型{tag}"


# ── 联系按钮构建（TG + WhatsApp 两个按钮）────────────────

def _contact_buttons(lang: str, vip: bool, user_id: int | None = None) -> list[InlineKeyboardButton]:
    import urllib.parse
    if vip:
        prefill = _vip_airfreight_prefill(user_id)
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


def _callback_tier(callback_data: InventoryCallback) -> str:
    return normalize_inventory_tier(callback_data.tier, callback_data.vip)


def _price_rate_notice(lang: str, rate: str) -> str:
    if rate:
        return _t(lang, "price_rate_notice").format(rate=escape(rate))
    return _t(lang, "price_rate_notice_no_rate")


def _price_rate_note(lang: str, rate: str) -> str:
    if rate:
        return _t(lang, "price_rate_note").format(rate=escape(rate))
    return _t(lang, "price_rate_note_no_rate")


async def _ensure_tier_access(
    callback: CallbackQuery,
    state: FSMContext | None,
    lang: str,
    tier: str,
) -> bool:
    access_key = inventory_tier_access_key(tier)
    if not access_key:
        return True
    if state and await has_hidden_access(state, access_key):
        return True
    if callback.message:
        await callback.message.edit_text(
            _t(lang, "menu_title"),
            reply_markup=inventory_menu_keyboard(lang),
        )
    await callback.answer(_t(lang, "access_expired"), show_alert=True)
    return False


def _price_brand_keyboard(brands: list[str], lang: str, tier: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for idx, brand in enumerate(brands, start=1):
        builder.row(InlineKeyboardButton(
            text=f"💰 {brand}",
            callback_data=InventoryCallback(action="price_brand", vip=True, tier=tier, page=idx).pack(),
        ))
    builder.row(InlineKeyboardButton(
        text={"zh": "⬅️ 返回", "en": "⬅️ Back", "ru": "⬅️ Назад"}.get(lang, "⬅️ 返回"),
        callback_data=InventoryCallback(action="tier_menu", vip=True, tier=tier).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 主菜单"),
        callback_data=NavCallback(action="home").pack(),
    ))
    return builder


def _price_result_keyboard(lang: str, tier: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text={"zh": "⬅️ 返回品牌", "en": "⬅️ Brands", "ru": "⬅️ Бренды"}.get(lang, "⬅️ 返回品牌"),
        callback_data=InventoryCallback(action="price_brands", vip=True, tier=tier).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 主菜单"),
        callback_data=NavCallback(action="home").pack(),
    ))
    return builder


def _price_view_mode_keyboard(lang: str, tier: str, brand_page: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=_t(lang, "price_table_mode"),
        callback_data=InventoryCallback(action="price_table", vip=True, tier=tier, page=brand_page).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=_t(lang, "price_image_mode"),
        callback_data=InventoryCallback(action="price_images", vip=True, tier=tier, page=brand_page).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "⬅️ 返回品牌", "en": "⬅️ Brands", "ru": "⬅️ Бренды"}.get(lang, "⬅️ 返回品牌"),
        callback_data=InventoryCallback(action="price_brands", vip=True, tier=tier).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 主菜单"),
        callback_data=NavCallback(action="home").pack(),
    ))
    return builder


def _price_field_labels(lang: str) -> dict[str, str]:
    return {
        "sku": {"zh": "SKU型号", "en": "SKU", "ru": "SKU"}.get(lang, "SKU型号"),
        "image": {"zh": "图片", "en": "Image", "ru": "Изображение"}.get(lang, "图片"),
        "description": {"zh": "描述", "en": "Description", "ru": "Описание"}.get(lang, "描述"),
        "moscow_stock": {"zh": "莫斯科库存", "en": "Moscow stock", "ru": "Склад Москва"}.get(lang, "莫斯科库存"),
        "status": {"zh": "状态", "en": "Status", "ru": "Статус"}.get(lang, "状态"),
        "none": {"zh": "暂无", "en": "N/A", "ru": "Нет данных"}.get(lang, "暂无"),
        "view_image": {"zh": "查看图片", "en": "View image", "ru": "Открыть изображение"}.get(lang, "查看图片"),
    }


def _currency_label(currency_key: str, lang: str) -> str:
    labels = {
        "rub": {"zh": "大约卢布", "en": "Approx. RUB", "ru": "Примерно в рублях"},
        "cny_ru": {
            "zh": "人民币（俄罗斯地址）",
            "en": "CNY (Russia address)",
            "ru": "Юань (адрес в России)",
        },
        "cny_cn": {
            "zh": "人民币（中国地址）",
            "en": "CNY (China address)",
            "ru": "Юань (адрес в Китае)",
        },
        "usd": {"zh": "美元价格", "en": "USD price", "ru": "Цена в USD"},
    }
    return labels.get(currency_key, {}).get(lang, labels.get(currency_key, {}).get("zh", currency_key))


def _format_price_line(currency_key: str, value: str, lang: str) -> str:
    label = _currency_label(currency_key, lang)
    display_value = value or {"zh": "未填写", "en": "not filled", "ru": "не указана"}.get(lang, "未填写")
    return f"{label}：<b>{escape(display_value)}</b>"


def _price_item_lines(item: OutdoorPriceItem, lang: str, tier: str, rate: str, image_text: str) -> list[str]:
    labels = _price_field_labels(lang)
    lines = [
        f"{labels['sku']}：<b>{escape(item.sku)}</b>",
        f"{labels['image']}：{image_text}",
    ]

    prices = item.prices or {}
    for currency_key in inventory_price_currency_keys(tier):
        lines.append(_format_price_line(currency_key, prices.get(currency_key, ""), lang))

    lines.append(f"{labels['moscow_stock']}：{escape(item.moscow_stock or labels['none'])}")
    lines.append(f"{labels['status']}：{escape(item.status or labels['none'])}")
    lines.append(_price_rate_note(lang, rate))
    return lines


def _price_item_message_text(item: OutdoorPriceItem, lang: str, tier: str, rate: str, image_text: str) -> str:
    return "\n".join(_price_item_lines(item, lang, tier, rate, image_text))


def _price_table_column_labels(lang: str) -> dict[str, str]:
    return {
        "sku": "SKU",
        "usd": {"zh": "美元", "en": "USD", "ru": "USD"}.get(lang, "美元"),
        "rub": {"zh": "卢布", "en": "RUB", "ru": "руб."}.get(lang, "卢布"),
        "cny_ru": {"zh": "俄址¥", "en": "RU ¥", "ru": "RU ¥"}.get(lang, "俄址¥"),
        "cny_cn": {"zh": "中址¥", "en": "CN ¥", "ru": "CN ¥"}.get(lang, "中址¥"),
        "stock": {"zh": "库存", "en": "Stock", "ru": "Склад"}.get(lang, "库存"),
        "status": {"zh": "状态", "en": "Status", "ru": "Статус"}.get(lang, "状态"),
    }


def _price_table_value(item: OutdoorPriceItem, key: str, none_text: str) -> str:
    if key == "sku":
        return item.sku or none_text
    if key == "stock":
        return item.moscow_stock or none_text
    if key == "status":
        return item.status or none_text
    return (item.prices or {}).get(key, "") or none_text


def _price_table_line(cells: list[tuple[str, int, str]]) -> list[str]:
    wrapped_cells = [_wrap_cell(value, width) for value, width, _ in cells]
    height = max(len(cell) for cell in wrapped_cells)
    lines: list[str] = []
    for line_idx in range(height):
        parts: list[str] = []
        for cell_idx, (_, width, align) in enumerate(cells):
            value = wrapped_cells[cell_idx][line_idx] if line_idx < len(wrapped_cells[cell_idx]) else ""
            parts.append(_right_cell(value, width) if align == "right" else _fit_cell(value, width))
        lines.append(" ".join(parts).rstrip())
    return lines


def _price_table_layout(lang: str, tier: str) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    labels = _price_table_column_labels(lang)
    first_line: list[tuple[str, int, str]] = [("sku", 10, "left")]
    if tier == "vvip":
        first_line.append(("usd", 5, "right"))
    first_line.append(("rub", 9, "right"))

    second_line: list[tuple[str, int, str]] = []
    if tier in {"svip", "vvip"}:
        second_line.extend((("cny_ru", 7, "right"), ("cny_cn", 7, "right")))
    second_line.extend((("stock", 5, "right"), ("status", 6, "left")))

    first_header = [(labels[key], width, align) for key, width, align in first_line]
    second_header = [(labels[key], width, align) for key, width, align in second_line]
    return first_header, second_header


def _price_table_rows(
    item: OutdoorPriceItem,
    lang: str,
    tier: str,
) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    labels = _price_field_labels(lang)
    first_header, second_header = _price_table_layout(lang, tier)
    first_line = [
        (_price_table_value(item, key, labels["none"]), width, align)
        for key, width, align in _price_table_keys(first_header, tier, first=True)
    ]
    second_line = [
        (_price_table_value(item, key, labels["none"]), width, align)
        for key, width, align in _price_table_keys(second_header, tier, first=False)
    ]
    return first_line, second_line


def _price_table_keys(
    header: list[tuple[str, int, str]],
    tier: str,
    *,
    first: bool,
) -> list[tuple[str, int, str]]:
    if first:
        keys: list[tuple[str, int, str]] = [("sku", header[0][1], header[0][2])]
        offset = 1
        if tier == "vvip":
            keys.append(("usd", header[offset][1], header[offset][2]))
            offset += 1
        keys.append(("rub", header[offset][1], header[offset][2]))
        return keys
    keys = []
    offset = 0
    if tier in {"svip", "vvip"}:
        keys.extend((
            ("cny_ru", header[offset][1], header[offset][2]),
            ("cny_cn", header[offset + 1][1], header[offset + 1][2]),
        ))
        offset += 2
    keys.extend((
        ("stock", header[offset][1], header[offset][2]),
        ("status", header[offset + 1][1], header[offset + 1][2]),
    ))
    return keys


def _format_price_table(items: list[OutdoorPriceItem], lang: str, tier: str) -> str:
    first_header, second_header = _price_table_layout(lang, tier)
    rows = [
        *_price_table_line(first_header),
        *_price_table_line(second_header),
        "\u2500" * 24,
    ]
    for item in items:
        first_line, second_line = _price_table_rows(item, lang, tier)
        rows.extend(_price_table_line(first_line))
        rows.extend(_price_table_line(second_line))
        rows.append("")
    if rows and rows[-1] == "":
        rows.pop()
    return f"<pre>{escape(chr(10).join(rows))}</pre>"


def _price_table_chunks(items: list[OutdoorPriceItem], lang: str, tier: str, max_len: int = 3000) -> list[str]:
    chunks: list[str] = []
    current: list[OutdoorPriceItem] = []
    for item in items:
        projected = [*current, item]
        if current and len(_format_price_table(projected, lang, tier)) > max_len:
            chunks.append(_format_price_table(current, lang, tier))
            current = [item]
        else:
            current = projected
    if current:
        chunks.append(_format_price_table(current, lang, tier))
    return chunks


async def _send_price_item_messages(
    callback: CallbackQuery,
    items: list[OutdoorPriceItem],
    lang: str,
    tier: str,
    rate: str,
) -> None:
    if not callback.message:
        return
    labels = _price_field_labels(lang)
    for item in items:
        if not item.image_url:
            text = _price_item_message_text(item, lang, tier, rate, labels["none"])
            await callback.message.answer(text)
            continue
        text = _price_item_message_text(item, lang, tier, rate, _t(lang, "price_image_attached"))
        try:
            await callback.message.answer_photo(photo=item.image_url, caption=text)
        except Exception as exc:
            logger.warning("send outdoor price photo failed sku=%s: %s", item.sku, exc)
            image_link = f"<a href=\"{escape(item.image_url, quote=True)}\">{labels['view_image']}</a>"
            fallback = _price_item_message_text(item, lang, tier, rate, image_link)
            await callback.message.answer(fallback)


async def _ensure_vip_access(
    callback: CallbackQuery,
    state: FSMContext | None,
    lang: str,
) -> bool:
    return await _ensure_tier_access(callback, state, lang, "vip")


async def _inventory_access_flags(state: FSMContext | None) -> dict[str, bool]:
    if not state:
        return {"vip": False, "svip": False, "vvip": False}
    return {
        "vip": await has_hidden_access(state, MENU_VIP_INVENTORY),
        "svip": await has_hidden_access(state, MENU_SVIP_INVENTORY),
        "vvip": await has_hidden_access(state, MENU_VVIP_INVENTORY),
    }


def _inventory_menu_with_flags(lang: str, flags: dict[str, bool]):
    return inventory_menu_keyboard(
        lang,
        vip_unlocked=flags["vip"],
        svip_unlocked=flags["svip"],
        vvip_unlocked=flags["vvip"],
    )


async def _show_tier_menu(callback: CallbackQuery, lang: str, tier: str) -> None:
    if not callback.message:
        return
    await callback.message.edit_text(
        _t(lang, "hidden_menu_title").format(tier=inventory_tier_label(tier)),
        reply_markup=inventory_hidden_menu_keyboard(lang, tier=tier),
    )


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
        await clear_state_keep_hidden_access(state)
    flags = await _inventory_access_flags(state)
    await callback.message.edit_text(
        _t(lang, "menu_title"),
        reply_markup=_inventory_menu_with_flags(lang, flags),
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


@router.callback_query(InventoryCallback.filter(F.action == "tier_menu"))
async def on_inventory_tier_menu(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    tier = _callback_tier(callback_data)
    if tier not in PRICE_TIER_CODES or not await _ensure_tier_access(callback, state, lang, tier):
        return
    await _show_tier_menu(callback, lang, tier)
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "categories"))
async def on_inventory_categories(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    tier = _callback_tier(callback_data)
    vip = tier != "public"
    if vip and not await _ensure_tier_access(callback, state, lang, tier):
        return
    title = (
        _t(lang, "tier_category_title").format(tier=inventory_tier_label(tier))
        if vip
        else _t(lang, "category_title")
    )
    await callback.message.edit_text(
        title,
        reply_markup=inventory_category_keyboard(lang, vip=vip, tier=tier if vip else ""),
    )
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "price_brands"))
async def on_inventory_price_brands(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    tier = _callback_tier(callback_data)
    if tier not in PRICE_TIER_CODES or not await _ensure_tier_access(callback, state, lang, tier):
        return

    brands = await get_outdoor_price_brand_titles()
    if not brands:
        await callback.message.edit_text(
            _t(lang, "price_loading_err"),
            reply_markup=inventory_hidden_menu_keyboard(lang, tier=tier),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        _t(lang, "price_brand_title").format(
            tier=inventory_tier_label(tier),
        ),
        reply_markup=_price_brand_keyboard(brands, lang, tier).as_markup(),
    )
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "price_brand"))
async def on_inventory_price_brand(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    tier = _callback_tier(callback_data)
    if tier not in PRICE_TIER_CODES or not await _ensure_tier_access(callback, state, lang, tier):
        return

    brands = await get_outdoor_price_brand_titles()
    brand_idx = callback_data.page - 1
    if brand_idx < 0 or brand_idx >= len(brands):
        await callback.answer(_t(lang, "price_loading_err"), show_alert=True)
        return
    brand = brands[brand_idx]
    await callback.message.edit_text(
        _t(lang, "price_view_title").format(
            tier=inventory_tier_label(tier),
            brand=escape(brand),
        ),
        reply_markup=_price_view_mode_keyboard(lang, tier, callback_data.page).as_markup(),
    )
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "price_images"))
async def on_inventory_price_images(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    tier = _callback_tier(callback_data)
    if tier not in PRICE_TIER_CODES or not await _ensure_tier_access(callback, state, lang, tier):
        return
    await callback.answer(_t(lang, "price_image_unavailable"), show_alert=True)


@router.callback_query(InventoryCallback.filter(F.action == "price_table"))
async def on_inventory_price_table(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    tier = _callback_tier(callback_data)
    if tier not in PRICE_TIER_CODES or not await _ensure_tier_access(callback, state, lang, tier):
        return

    brands = await get_outdoor_price_brand_titles()
    brand_idx = callback_data.page - 1
    if brand_idx < 0 or brand_idx >= len(brands):
        await callback.answer(_t(lang, "price_loading_err"), show_alert=True)
        return
    brand = brands[brand_idx]
    items, rate = await get_outdoor_price_items(brand, tier)

    if not items:
        await callback.message.edit_text(
            _t(lang, "price_empty"),
            reply_markup=_price_view_mode_keyboard(lang, tier, callback_data.page).as_markup(),
        )
        await callback.answer()
        return

    table_chunks = _price_table_chunks(items, lang, tier)
    first_text = "\n\n".join((
        _t(lang, "price_selected_brand").format(
            tier=inventory_tier_label(tier),
            brand=escape(brand),
        ),
        _price_rate_notice(lang, rate),
        _t(lang, "price_result_header").format(count=len(items)),
        table_chunks[0],
        _price_rate_note(lang, rate),
    ))
    await callback.message.edit_text(
        first_text,
        reply_markup=_price_result_keyboard(lang, tier).as_markup(),
        disable_web_page_preview=True,
    )
    await callback.answer()
    for table_chunk in table_chunks[1:]:
        await callback.message.answer(table_chunk)
    await callback.message.answer(
        _t(lang, "price_done_prompt"),
        reply_markup=_price_result_keyboard(lang, tier).as_markup(),
    )


@router.callback_query(InventoryCallback.filter(F.action == "category"))
async def on_inventory_category(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """品类选择后展示品牌列表."""
    if not callback.message:
        return

    tier = _callback_tier(callback_data)
    vip = tier != "public"
    cat_id = callback_data.cat_id
    if vip and not await _ensure_tier_access(callback, state, lang, tier):
        return

    if cat_id != "outdoor":
        await callback.answer("Coming soon", show_alert=True)
        return

    if not settings.outdoor_sheet_id:
        await callback.message.edit_text(_t(lang, "not_configured"))
        await callback.answer()
        return

    try:
        items = await get_outdoor_inventory(vip=vip, tier=tier)
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
        reply_markup=_brand_keyboard(items, lang, vip, tier).as_markup(),
    )
    await callback.answer()


@router.callback_query(InventoryCallback.filter(F.action == "brand"))
async def on_inventory_brand(
    callback: CallbackQuery,
    callback_data: InventoryCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """品牌选择后展示该品牌库存."""
    if not callback.message:
        return

    tier = _callback_tier(callback_data)
    vip = tier != "public"
    if vip and not await _ensure_tier_access(callback, state, lang, tier):
        return

    if not settings.outdoor_sheet_id:
        await callback.message.edit_text(_t(lang, "not_configured"))
        await callback.answer()
        return

    try:
        items = await get_outdoor_inventory(vip=vip, tier=tier)
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
    brand_items = _stock_first(_filter_brand_items(items, brand, lang))
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
        callback_data=InventoryCallback(action="category", cat_id="outdoor", vip=vip, tier=tier).pack(),
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
    state: FSMContext | None = None,
) -> None:
    """快速展示所有品牌中当前有货的库存."""
    if not callback.message:
        return

    tier = _callback_tier(callback_data)
    vip = tier != "public"
    if vip and not await _ensure_tier_access(callback, state, lang, tier):
        return

    if not settings.outdoor_sheet_id:
        await callback.message.edit_text(_t(lang, "not_configured"))
        await callback.answer()
        return

    try:
        items = await get_outdoor_inventory(vip=vip, tier=tier)
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
            callback_data=InventoryCallback(action="category", cat_id="outdoor", vip=vip, tier=tier).pack(),
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
        callback_data=InventoryCallback(action="category", cat_id="outdoor", vip=vip, tier=tier).pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 Main Menu"),
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()
