"""Vandych VIP 隐藏菜单.

触发方式：用户在任意时刻发送 Vandych 密码（ABFVandych2026XXA）→ 显示隐藏菜单。
功能：
1. 获取折扣 — 读取促销折扣表，返回链接 + 折扣码
2. 支付空运 — 发送速卖通空运支付链接 + 折扣码
3. 我需要批发 — 输入型号 + 数量（FSM），≥5件→VIP优先人工，<5件→普通需求
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import NavCallback, VipCallback
from bot.keyboards.inline import vip_menu_keyboard
from bot.services.discount_sheet import fuzzy_find, get_discounts
from bot.states.vip import VipStates

logger = logging.getLogger(__name__)
router = Router(name="vip")

TEXTS: dict[str, dict[str, str]] = {
    "zh": {
        "welcome": (
            "⛺ <b>Vandych 的帐篷</b>\n\n"
            "欢迎！请选择您需要的服务："
        ),
        "discount_title": "🎁 <b>促销折扣</b>\n\n当前有效折扣：\n\n",
        "discount_empty": "📭 当前暂无促销折扣。",
        "discount_note": "\n\n⚠️ <i>提示：以上折扣仅本次促销有效</i>",
        "shipping_text": "✈️ <b>空运支付</b>\n\n请通过以下链接完成空运费用支付：",
        "shipping_no_url": "⚠️ 空运支付链接暂未配置，请联系客服。",
        "wholesale_enter": "📦 <b>批发需求</b>\n\n请输入您的型号和采购数量，格式：\n<code>型号 数量</code>\n\n例如：<code>ABC-100 10</code>",
        "wholesale_parse_err": "❌ 格式错误，请按「型号 数量」输入，例如：<code>ABC-100 5</code>",
        "wholesale_vip": "✅ <b>≥5件 — VIP 优先处理</b>\n\n已记录您的批发需求，客服将优先与您联系：",
        "wholesale_normal": "📋 <b>批发需求已记录</b>\n\n客服将尽快与您联系：",
        "contact_vip": "💬 VIP 优先客服",
        "contact_normal": "💬 联系客服",
        "loading_err": "❌ 读取折扣信息失败，请稍后重试。",
    },
    "en": {
        "welcome": (
            "⛺ <b>Vandych's tent</b>\n\n"
            "Welcome! Select a service:"
        ),
        "discount_title": "🎁 <b>Promotions</b>\n\nActive discounts:\n\n",
        "discount_empty": "📭 No active promotions at the moment.",
        "discount_note": "\n\n⚠️ <i>Note: Discounts are valid for this promotion only</i>",
        "shipping_text": "✈️ <b>Air Freight Payment</b>\n\nPay via the link below:",
        "shipping_no_url": "⚠️ Air freight link not configured. Contact support.",
        "wholesale_enter": "📦 <b>Wholesale Request</b>\n\nEnter model and quantity:\n<code>Model Quantity</code>\n\nExample: <code>ABC-100 10</code>",
        "wholesale_parse_err": "❌ Format error. Use: <code>Model Qty</code>, e.g. <code>ABC-100 5</code>",
        "wholesale_vip": "✅ <b>≥5 units — VIP Priority</b>\n\nYour request is recorded. Support will contact you with priority:",
        "wholesale_normal": "📋 <b>Wholesale Request Recorded</b>\n\nSupport will contact you shortly:",
        "contact_vip": "💬 VIP Support",
        "contact_normal": "💬 Contact Support",
        "loading_err": "❌ Failed to load discounts. Please try again.",
    },
    "ru": {
        "welcome": (
            "⛺ <b>Палатка Вандыча</b>\n\n"
            "Добро пожаловать! Выберите услугу:"
        ),
        "discount_title": "🎁 <b>Акции</b>\n\nАктивные скидки:\n\n",
        "discount_empty": "📭 Нет активных акций.",
        "discount_note": "\n\n⚠️ <i>Скидки действуют только в рамках текущей акции</i>",
        "shipping_text": "✈️ <b>Оплата авиадоставки</b>\n\nОплатите по ссылке ниже:",
        "shipping_no_url": "⚠️ Ссылка авиадоставки не настроена.",
        "wholesale_enter": "📦 <b>Оптовый запрос</b>\n\nВведите модель и количество:\n<code>Модель Кол-во</code>\n\nПример: <code>ABC-100 10</code>",
        "wholesale_parse_err": "❌ Неверный формат. Используйте: <code>Модель Кол-во</code>",
        "wholesale_vip": "✅ <b>≥5 единиц — VIP приоритет</b>\n\nЗапрос записан. Поддержка свяжется с вами в приоритетном порядке:",
        "wholesale_normal": "📋 <b>Оптовый запрос записан</b>\n\nПоддержка скоро свяжется:",
        "contact_vip": "💬 VIP поддержка",
        "contact_normal": "💬 Поддержка",
        "loading_err": "❌ Ошибка загрузки скидок. Попробуйте позже.",
    },
}


def _t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"].get(key, key))


def _agent_url(prefill: str) -> str:
    import urllib.parse
    return f"https://t.me/{settings.human_agent_username}?text={urllib.parse.quote(prefill)}"


# ── 密码触发（自由文本消息）──────────────────────────────

@router.message(F.text)
async def on_vandych_password_catch(
    message: Message,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """捕获 Vandych 密码（最低优先级 handler，仅在其他 handler 未匹配时触发）."""
    text = (message.text or "").strip()
    if text != settings.vandych_password:
        return  # 不是密码，不处理（交由其他 handler 或被忽略）
    if state:
        await state.clear()
    await message.answer(_t(lang, "welcome"), reply_markup=vip_menu_keyboard(lang))


# ── VIP 菜单回调 ─────────────────────────────────────────

@router.callback_query(VipCallback.filter(F.action == "menu"))
async def on_vip_menu(callback: CallbackQuery, lang: str = "zh") -> None:
    if not callback.message:
        return
    await callback.message.edit_text(_t(lang, "welcome"), reply_markup=vip_menu_keyboard(lang))
    await callback.answer()


@router.callback_query(VipCallback.filter(F.action == "discount"))
async def on_vip_discount(callback: CallbackQuery, lang: str = "zh") -> None:
    """展示 SKU 列表按钮，供用户选择."""
    if not callback.message:
        return
    try:
        items = await get_discounts()
    except Exception as e:
        logger.error("get_discounts failed: %s", e)
        await callback.answer(_t(lang, "loading_err"), show_alert=True)
        return

    nav = InlineKeyboardBuilder()
    nav.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回", "en": "◀️ Back", "ru": "◀️ Назад"}.get(lang, "◀️"),
        callback_data=VipCallback(action="menu").pack(),
    ))
    nav.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠"),
        callback_data=NavCallback(action="home").pack(),
    ))

    if not items:
        await callback.message.edit_text(_t(lang, "discount_empty"), reply_markup=nav.as_markup())
        await callback.answer()
        return

    title = {
        "zh": "🎁 <b>请选择产品</b>\n\n点击下方 SKU 获取专属折扣信息：",
        "en": "🎁 <b>Select a product</b>\n\nTap an SKU below to get your exclusive discount:",
        "ru": "🎁 <b>Выберите товар</b>\n\nНажмите на SKU ниже, чтобы получить скидку:",
    }.get(lang, "")

    builder = InlineKeyboardBuilder()
    for idx, item in enumerate(items):
        builder.row(InlineKeyboardButton(
            text=f"🏷 {item.model}",
            callback_data=VipCallback(action="sku_select", sku_idx=idx).pack(),
        ))
    for btn_row in nav.buttons:
        builder.row(*btn_row)

    await callback.message.edit_text(title, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(VipCallback.filter(F.action == "sku_select"))
async def on_sku_select(
    callback: CallbackQuery,
    callback_data: VipCallback,
    lang: str = "zh",
) -> None:
    """用户点击 SKU 按钮后，发送可复制的折扣信息."""
    if not callback.message:
        return
    try:
        items = await get_discounts()
    except Exception as e:
        logger.error("get_discounts failed: %s", e)
        await callback.answer(_t(lang, "loading_err"), show_alert=True)
        return

    idx = callback_data.sku_idx
    if idx < 0 or idx >= len(items):
        await callback.answer("❌ 数据已更新，请重新选择", show_alert=True)
        return

    item = items[idx]
    text = item.format_copyable(lang) + _t(lang, "discount_note")

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回列表", "en": "◀️ Back to list", "ru": "◀️ К списку"}.get(lang, "◀️"),
        callback_data=VipCallback(action="discount").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠"),
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(VipCallback.filter(F.action == "shipping"))
async def on_vip_shipping(callback: CallbackQuery, lang: str = "zh") -> None:
    if not callback.message:
        return
    url = settings.aliexpress_shipping_url
    builder = InlineKeyboardBuilder()
    if url and "aliexpress.com" in url and url != "https://www.aliexpress.com":
        builder.row(InlineKeyboardButton(
            text={"zh": "🛒 前往支付", "en": "🛒 Pay Now", "ru": "🛒 Оплатить"}.get(lang, "🛒"),
            url=url,
        ))
        text = _t(lang, "shipping_text")
    else:
        text = _t(lang, "shipping_no_url")
    for row in [
        [InlineKeyboardButton(
            text={"zh": "◀️ 返回", "en": "◀️ Back", "ru": "◀️ Назад"}.get(lang, "◀️"),
            callback_data=VipCallback(action="menu").pack(),
        )],
    ]:
        builder.row(*row)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(VipCallback.filter(F.action == "wholesale"))
async def on_vip_wholesale_enter(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message or not state:
        return
    await state.set_state(VipStates.awaiting_wholesale_input)
    await state.update_data(lang=lang)
    await callback.message.edit_text(_t(lang, "wholesale_enter"))
    await callback.answer()


@router.message(VipStates.awaiting_wholesale_input)
async def on_wholesale_input(
    message: Message,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not state:
        return
    await state.clear()
    text = (message.text or "").strip()
    parts = text.rsplit(None, 1)  # 从右侧分割，最后一个空格分隔数量

    if len(parts) != 2:
        await message.answer(_t(lang, "wholesale_parse_err"))
        return

    model_str, qty_str = parts
    try:
        qty = int(qty_str)
    except ValueError:
        await message.answer(_t(lang, "wholesale_parse_err"))
        return

    user_id = message.from_user.id if message.from_user else 0
    user_name = message.from_user.username or str(user_id) if message.from_user else str(user_id)

    if qty >= 5:
        prefill = {
            "zh": f"你好，我是VIP批发客户 @{user_name}，需要批发 {model_str} x{qty}，请优先处理",
            "en": f"Hi, I'm VIP wholesale @{user_name}, need {model_str} x{qty}, priority please",
            "ru": f"Привет, VIP-оптовик @{user_name}, нужно {model_str} x{qty}, приоритет",
        }.get(lang, f"VIP wholesale @{user_name} {model_str} x{qty}")
        result_key = "wholesale_vip"
        btn_key = "contact_vip"
    else:
        prefill = {
            "zh": f"你好，我需要批发 {model_str} x{qty} (@{user_name})",
            "en": f"Hi, wholesale inquiry {model_str} x{qty} (@{user_name})",
            "ru": f"Привет, оптовый запрос {model_str} x{qty} (@{user_name})",
        }.get(lang, f"Wholesale {model_str} x{qty} @{user_name}")
        result_key = "wholesale_normal"
        btn_key = "contact_normal"

    summary = f"\n\n• 型号/Model: <b>{model_str}</b>\n• 数量/Qty: <b>{qty}</b>"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=_t(lang, btn_key), url=_agent_url(prefill)))
    builder.row(InlineKeyboardButton(
        text={"zh": "◀️ 返回VIP菜单", "en": "◀️ Back to VIP Menu", "ru": "◀️ Назад"}.get(lang, "◀️"),
        callback_data=VipCallback(action="menu").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠"),
        callback_data=NavCallback(action="home").pack(),
    ))
    await message.answer(_t(lang, result_key) + summary, reply_markup=builder.as_markup())
