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
        "stock_title_public": "📦 <b>莫斯科 · 户外类现货</b>（公开库存）\n\n",
        "stock_title_vip": "⭐ <b>莫斯科 · 户外类现货</b>（VIP 完整库存）\n\n",
        "no_stock_public": "❌ 当前暂无公开库存。\n\n如需进一步了解，请联系客服：",
        "no_stock_vip": "❌ 当前暂无库存（含空运预约）。\n\n如需预约空运，请联系：",
        "available": "✅ 有货",
        "out_of_stock": "❌ 无货",
        "contact_cs": "💬 联系客服",
        "contact_air": "✈️ 预约空运",
        "data_delay": "\n\n<i>数据可能有 5 分钟缓存延迟</i>",
        "loading_err": "❌ 读取库存失败，请稍后重试。",
        "not_configured": "⚠️ 库存服务暂未配置，请稍后再试。",
    },
    "en": {
        "menu_title": "🔍 <b>Moscow Inventory Query</b>\n\nSelect query type:",
        "category_title": "📂 Select category:",
        "stock_title_public": "📦 <b>Moscow · Outdoor Stock</b> (Public)\n\n",
        "stock_title_vip": "⭐ <b>Moscow · Outdoor Stock</b> (VIP Full View)\n\n",
        "no_stock_public": "❌ No public inventory available.\n\nContact support:",
        "no_stock_vip": "❌ No inventory available (incl. air freight).\n\nTo book air freight:",
        "available": "✅ In stock",
        "out_of_stock": "❌ Out of stock",
        "contact_cs": "💬 Contact Support",
        "contact_air": "✈️ Book Air Freight",
        "data_delay": "\n\n<i>Data may be up to 5 minutes delayed</i>",
        "loading_err": "❌ Failed to load inventory. Please try again.",
        "not_configured": "⚠️ Inventory service not configured yet.",
    },
    "ru": {
        "menu_title": "🔍 <b>Наличие в Москве</b>\n\nВыберите тип запроса:",
        "category_title": "📂 Выберите категорию:",
        "stock_title_public": "📦 <b>Москва · Аутдор — наличие</b> (общий)\n\n",
        "stock_title_vip": "⭐ <b>Москва · Аутдор — наличие</b> (VIP полный список)\n\n",
        "no_stock_public": "❌ Публичный список пуст.\n\nСвяжитесь с поддержкой:",
        "no_stock_vip": "❌ Нет в наличии (включая авиа).\n\nДля заказа авиадоставки:",
        "available": "✅ В наличии",
        "out_of_stock": "❌ Нет в наличии",
        "contact_cs": "💬 Поддержка",
        "contact_air": "✈️ Заказать авиа",
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
    """生成户外库存表格 HTML（<pre> 包裹）."""
    if not items:
        return ""

    hdr = {
        "zh": ("型号", "数量", "状态"),
        "en": ("Model", "Qty", "Status"),
        "ru": ("Модель", "Кол-во", "Статус"),
    }.get(lang, ("型号", "数量", "状态"))

    names = [i.name or i.sku for i in items]
    qtys = [str(i.qty) for i in items]
    statuses = [i.status_text(lang) for i in items]

    name_w = max(_display_width(hdr[0]), min(max(_display_width(n) for n in names), 14))
    qty_w = max(_display_width(hdr[1]), max(_display_width(q) for q in qtys))
    status_w = max(_display_width(hdr[2]), max(_display_width(s) for s in statuses))

    header = f"{_fit_cell(hdr[0], name_w)} {_right_cell(hdr[1], qty_w)} {_fit_cell(hdr[2], status_w)}"
    sep = "─" * (name_w + qty_w + status_w + 2)

    rows = [header]
    for idx, item in enumerate(items):
        name_lines = _wrap_cell(item.name or item.sku, name_w)
        qty_lines = _wrap_cell(str(item.qty), qty_w)
        status_lines = _wrap_cell(item.status_text(lang), status_w)
        h = max(len(name_lines), len(qty_lines), len(status_lines))
        for i in range(h):
            nv = name_lines[i] if i < len(name_lines) else ""
            qv = qty_lines[i] if i < len(qty_lines) else ""
            sv = status_lines[i] if i < len(status_lines) else ""
            rows.append(f"{_fit_cell(nv, name_w)} {_right_cell(qv, qty_w)} {_fit_cell(sv, status_w)}")
        if item.notes:
            rows.append(f"  📝 {item.notes}")
        if idx < len(items) - 1:
            rows.append(sep)

    return f"<pre>{escape(chr(10).join(rows))}</pre>"


# ── 联系客服 URL 构建 ────────────────────────────────────

def _agent_url(prefill: str) -> str:
    import urllib.parse
    username = settings.human_agent_username
    return f"https://t.me/{username}?text={urllib.parse.quote(prefill)}"


def _contact_button(lang: str, vip: bool, user_id: int | None = None) -> InlineKeyboardButton:
    tag = f" (TGID:{user_id})" if user_id else ""
    if vip:
        key = "contact_air"
        prefill = {
            "zh": f"你好，我需要预约空运{tag}",
            "en": f"Hi, I'd like to book air freight{tag}",
            "ru": f"Привет, хочу заказать авиадоставку{tag}",
        }.get(lang, "Hi, air freight inquiry")
    else:
        key = "contact_cs"
        prefill = {
            "zh": f"你好，我想查询库存{tag}",
            "en": f"Hi, I'd like to check stock{tag}",
            "ru": f"Привет, хочу узнать наличие{tag}",
        }.get(lang, "Hi, stock inquiry")
    return InlineKeyboardButton(text=_t(lang, key), url=_agent_url(prefill))


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
    """品类选择后展示库存."""
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

    title_key = "stock_title_vip" if vip else "stock_title_public"
    builder = InlineKeyboardBuilder()

    if not items:
        user_id = callback.from_user.id if callback.from_user else None
        builder.row(_contact_button(lang, vip, user_id))
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

    table_html = _format_outdoor_table(items, lang)
    text = _t(lang, title_key) + table_html + _t(lang, "data_delay")
    if len(text) > 4000:
        text = text[:3900] + "\n…"

    user_id = callback.from_user.id if callback.from_user else None
    builder.row(_contact_button(lang, vip, user_id))
    builder.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回查询方式", "en": "◀️ Back", "ru": "◀️ Назад"}.get(lang, "◀️ Back"),
        callback_data=InventoryCallback(action="menu").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 Main Menu"),
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()
