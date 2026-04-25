"""Vandych VIP 隐藏菜单.

触发方式：用户在任意时刻发送 Vandych 密码（ABFVandych2026XXA）→ 显示隐藏菜单。
功能：
1. 获取折扣 — 读取促销折扣表，返回链接 + 折扣码
2. 支付空运 — 发送速卖通空运支付链接 + 折扣码
3. 我需要批发 — 输入型号 + 数量（FSM），≥5件→VIP优先人工，<5件→普通需求
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import NavCallback, VipCallback
from bot.keyboards.inline import vip_menu_keyboard
from bot.services.discount_sheet import get_discounts
from bot.services.notification import notification_service
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
        "shipping_code": "\n\n🎟 <b>折扣码：</b><code>{code}</code>",
        "shipping_no_url": "⚠️ 空运支付链接暂未配置，请联系客服。",
        "wholesale_enter": "📦 <b>批发需求</b>\n\n请输入您的型号和采购数量，格式：\n<code>型号 数量</code>\n\n例如：<code>ABC-100 10</code>",
        "wholesale_parse_err": "❌ 格式错误，请按「型号 数量」输入，例如：<code>ABC-100 5</code>",
        "wholesale_vip": "✅ <b>已标记：VIP 客户 + 优先人工</b>\n\n请点击下方按钮转接专属客服。",
        "wholesale_normal": "📋 <b>已标记：普通批发需求</b>\n\n请点击下方按钮转接专属客服。",
        "contact_vip": "💬 转接 VIP 专属客服",
        "contact_normal": "💬 转接专属客服",
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
        "shipping_code": "\n\n🎟 <b>Discount code:</b><code>{code}</code>",
        "shipping_no_url": "⚠️ Air freight link not configured. Contact support.",
        "wholesale_enter": "📦 <b>Wholesale Request</b>\n\nEnter model and quantity:\n<code>Model Quantity</code>\n\nExample: <code>ABC-100 10</code>",
        "wholesale_parse_err": "❌ Format error. Use: <code>Model Qty</code>, e.g. <code>ABC-100 5</code>",
        "wholesale_vip": "✅ <b>Marked: VIP customer + priority support</b>\n\nTap the button below to contact dedicated support.",
        "wholesale_normal": "📋 <b>Marked: normal wholesale request</b>\n\nTap the button below to contact dedicated support.",
        "contact_vip": "💬 VIP Dedicated Support",
        "contact_normal": "💬 Dedicated Support",
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
        "shipping_code": "\n\n🎟 <b>Промокод:</b><code>{code}</code>",
        "shipping_no_url": "⚠️ Ссылка авиадоставки не настроена.",
        "wholesale_enter": "📦 <b>Оптовый запрос</b>\n\nВведите модель и количество:\n<code>Модель Кол-во</code>\n\nПример: <code>ABC-100 10</code>",
        "wholesale_parse_err": "❌ Неверный формат. Используйте: <code>Модель Кол-во</code>",
        "wholesale_vip": "✅ <b>Отмечено: VIP клиент + приоритет</b>\n\nНажмите кнопку ниже, чтобы связаться с отдельной поддержкой.",
        "wholesale_normal": "📋 <b>Отмечено: обычный оптовый запрос</b>\n\nНажмите кнопку ниже, чтобы связаться с отдельной поддержкой.",
        "contact_vip": "💬 VIP поддержка",
        "contact_normal": "💬 Отдельная поддержка",
        "loading_err": "❌ Ошибка загрузки скидок. Попробуйте позже.",
    },
}


def _t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"].get(key, key))


def _agent_username() -> str:
    return settings.vandych_agent_username.strip() or settings.human_agent_username


def _agent_url(prefill: str) -> str:
    import urllib.parse
    return f"https://t.me/{_agent_username()}?text={urllib.parse.quote(prefill)}"


def _is_real_url(url: str) -> bool:
    import urllib.parse

    normalized = url.strip().rstrip("/")
    placeholders = {
        "",
        "https://www.aliexpress.com",
        "http://www.aliexpress.com",
        "https://aliexpress.com",
        "http://aliexpress.com",
    }
    if normalized in placeholders:
        return False
    parsed = urllib.parse.urlparse(normalized)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _shipping_payment_url() -> str:
    shipping_url = settings.aliexpress_shipping_url.strip()
    if _is_real_url(shipping_url):
        return shipping_url

    store_url = settings.aliexpress_store_url.strip()
    if _is_real_url(store_url):
        return store_url

    return ""


def _airfreight_prefill(user_id: int | None) -> str:
    tag = f"，TGID:{user_id}" if user_id else ""
    return f"你好，我需要了解航空货运服务。来源：Vandych的帐篷{tag}"


def _is_vandych_password(text: str | None) -> bool:
    return bool(text and text.strip() == settings.vandych_password)


def _user_tag(message: Message) -> str:
    if not message.from_user:
        return ""
    if message.from_user.username:
        return f"@{message.from_user.username}"
    full_name = " ".join(part for part in (message.from_user.first_name, message.from_user.last_name) if part)
    return full_name or str(message.from_user.id)


def _wholesale_request_type(qty: int, lang: str = "zh") -> str:
    if qty >= 5:
        return {
            "zh": "VIP批发优先",
            "en": "VIP wholesale priority",
            "ru": "VIP опт — приоритет",
        }.get(lang, "VIP批发优先")
    return {
        "zh": "普通批发需求",
        "en": "Normal wholesale request",
        "ru": "Обычный оптовый запрос",
    }.get(lang, "普通批发需求")


def _wholesale_plain_text(message: Message, model: str, qty: int) -> str:
    user_id = message.from_user.id if message.from_user else 0
    user_tag = _user_tag(message) or str(user_id)
    request_type = _wholesale_request_type(qty, "zh")
    return (
        "你好，我需要批发咨询。\n"
        "来源：Vandych的帐篷\n"
        f"请求类型：{request_type}\n"
        f"TGID:{user_id}\n"
        f"用户：{user_tag}\n"
        f"型号：{model}\n"
        f"数量：{qty}"
    )


def _wholesale_html_summary(message: Message, model: str, qty: int, lang: str = "zh") -> str:
    user_id = message.from_user.id if message.from_user else 0
    user_tag = _user_tag(message) or str(user_id)
    request_type = _wholesale_request_type(qty, lang)
    labels = {
        "zh": ("来源", "请求类型", "用户", "型号/Model", "数量/Qty", "Vandych的帐篷"),
        "en": ("Source", "Request type", "User", "Model", "Qty", "Vandych's tent"),
        "ru": ("Источник", "Тип запроса", "Пользователь", "Модель", "Кол-во", "Палатка Вандыча"),
    }.get(lang, ("来源", "请求类型", "用户", "型号/Model", "数量/Qty", "Vandych的帐篷"))
    sep = "：" if lang == "zh" else ": "
    return (
        "\n\n"
        f"• {labels[0]}{sep}<code>{escape(labels[5])}</code>\n"
        f"• {labels[1]}{sep}<code>{escape(request_type)}</code>\n"
        f"• TGID{sep}<code>{user_id}</code>\n"
        f"• {labels[2]}{sep}<code>{escape(user_tag)}</code>\n"
        f"• {labels[3]}{sep}<b>{escape(model)}</b>\n"
        f"• {labels[4]}{sep}<b>{qty}</b>"
    )


async def _notify_wholesale_request(message: Message, model: str, qty: int) -> None:
    notice = (
        "📦 <b>Vandych 的帐篷批发需求</b>\n\n"
        + _wholesale_html_summary(message, model, qty, "zh").lstrip()
    )
    try:
        if qty >= 5 and notification_service.escalation_agent_id:
            await notification_service.notify_escalation_agent(notice, message.from_user.id if message.from_user else None)
        elif notification_service.support_group_id:
            await notification_service.notify_support_group(notice, message.from_user.id if message.from_user else None)
    except Exception as e:
        logger.warning("notify wholesale request failed: %s", e)


# ── 密码触发（自由文本消息）──────────────────────────────

@router.message(StateFilter(default_state), F.text.func(_is_vandych_password))
async def on_vandych_password_catch(
    message: Message,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """捕获 Vandych 密码（最低优先级 handler，仅在其他 handler 未匹配时触发）."""
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
    url = _shipping_payment_url()
    code = settings.vandych_shipping_discount_code.strip()
    builder = InlineKeyboardBuilder()
    if url:
        builder.row(InlineKeyboardButton(
            text={"zh": "🛒 前往支付", "en": "🛒 Pay Now", "ru": "🛒 Оплатить"}.get(lang, "🛒"),
            url=url,
        ))
        text = _t(lang, "shipping_text")
        if code:
            text += _t(lang, "shipping_code").format(code=escape(code))
    else:
        text = _t(lang, "shipping_no_url")
        user_id = callback.from_user.id if callback.from_user else None
        builder.row(InlineKeyboardButton(
            text={"zh": "💬 联系专属客服", "en": "💬 Contact Support", "ru": "💬 Поддержка"}.get(lang, "💬"),
            url=_agent_url(_airfreight_prefill(user_id)),
        ))
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
    if qty <= 0:
        await message.answer(_t(lang, "wholesale_parse_err"))
        return

    await state.clear()

    if qty >= 5:
        result_key = "wholesale_vip"
        btn_key = "contact_vip"
    else:
        result_key = "wholesale_normal"
        btn_key = "contact_normal"

    await _notify_wholesale_request(message, model_str, qty)

    prefill = _wholesale_plain_text(message, model_str, qty)
    summary = _wholesale_html_summary(message, model_str, qty, lang)
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
