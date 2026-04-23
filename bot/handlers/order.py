"""售中下单 — 产品类型选择 → 子分类 → 转人工 / 跳转速卖通 / 批发留言.

流程（来自设计稿粉色部分）：
  售中下单 → 询问产品类型
  ├── 热成像仪 → 选子类
  │   ├── 工业      → 转特定人工 1
  │   └── 狩猎/特殊  → 转特定人工 2
  ├── 动力工具 → 跳转速卖通店铺
  └── 批发订单 → 留言数量和型号 → 带留言转人工
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import NavCallback, OrderCallback
from bot.keyboards.inline import (
    order_product_type_keyboard,
    order_thermal_subcategory_keyboard,
)
from bot.services.notification import notification_service
from bot.states.order import OrderStates

logger = logging.getLogger(__name__)
router = Router(name="order")


# ── 多语言文案 ──────────────────────────────────────────

TEXTS = {
    "zh": {
        "type_title": "📦 售中下单\n\n请选择产品类型：",
        "thermal_sub_title": "🌡 <b>热成像仪</b>\n\n请选择子分类：",
        "aliexpress_title": (
            "⚡ <b>动力工具</b>\n\n"
            "动力工具请访问速卖通店铺下单：\n\n"
            "👇 点击下方按钮前往店铺"
        ),
        "wholesale_prompt": (
            "📦 <b>批发订单</b>\n\n"
            "请输入您需要的商品 <b>数量和型号</b>：\n\n"
            "（直接发送文字消息即可，例如：\n"
            "<i>DP9 工业热成像仪 × 20台</i>）"
        ),
        "transfer_success": (
            "✅ 您的需求已转接到专属客服。\n\n"
            "客服将在工作时间内尽快回复，请耐心等待。\n"
            "如有紧急问题，请直接联系客服。"
        ),
        "transfer_fail": "⚠️ 转接失败，请稍后重试或联系管理员。",
        "wholesale_sent": (
            "✅ 您的批发订单留言已提交！\n\n"
            "📝 <b>留言内容：</b>\n<i>{message}</i>\n\n"
            "客服将在工作时间内尽快回复。"
        ),
        "wholesale_cancel": "❌ 已取消批发下单。",
        "agent_notify": (
            "📦 <b>售中下单 — {category}</b>\n\n"
            "👤 用户: {user_name} (ID: <code>{user_id}</code>)\n"
            "📂 分类: {category}\n"
        ),
        "agent_wholesale_notify": (
            "📦 <b>批发订单留言</b>\n\n"
            "👤 用户: {user_name} (ID: <code>{user_id}</code>)\n"
            "📝 留言: <i>{message}</i>\n"
        ),
        "shop_btn": "🛒 前往速卖通店铺",
        "nav_back_type": "◀️ 返回产品类型",
        "nav_home": "🏠 返回主菜单",
    },
    "en": {
        "type_title": "📦 Place Order\n\nSelect product type:",
        "thermal_sub_title": "🌡 <b>Thermal Imager</b>\n\nSelect subcategory:",
        "aliexpress_title": (
            "⚡ <b>Power Tools</b>\n\n"
            "Please visit our AliExpress store:\n\n"
            "👇 Click below to visit"
        ),
        "wholesale_prompt": (
            "📦 <b>Wholesale Order</b>\n\n"
            "Enter the <b>quantity and model</b>:\n\n"
            "(Send a text message, e.g.:\n"
            "<i>DP9 Thermal Imager × 20pcs</i>)"
        ),
        "transfer_success": (
            "✅ Your request has been forwarded.\n\n"
            "Our agent will reply ASAP during business hours."
        ),
        "transfer_fail": "⚠️ Transfer failed, please try again later.",
        "wholesale_sent": (
            "✅ Your wholesale order has been submitted!\n\n"
            "📝 <b>Message:</b>\n<i>{message}</i>\n\n"
            "Our agent will reply ASAP."
        ),
        "wholesale_cancel": "❌ Wholesale order cancelled.",
        "agent_notify": (
            "📦 <b>Order — {category}</b>\n\n"
            "👤 User: {user_name} (ID: <code>{user_id}</code>)\n"
            "📂 Category: {category}\n"
        ),
        "agent_wholesale_notify": (
            "📦 <b>Wholesale Order</b>\n\n"
            "👤 User: {user_name} (ID: <code>{user_id}</code>)\n"
            "📝 Message: <i>{message}</i>\n"
        ),
        "shop_btn": "🛒 Visit AliExpress Store",
        "nav_back_type": "◀️ Back to types",
        "nav_home": "🏠 Main Menu",
    },
    "ru": {
        "type_title": "📦 Заказ\n\nВыберите тип продукта:",
        "thermal_sub_title": "🌡 <b>Тепловизор</b>\n\nВыберите подкатегорию:",
        "aliexpress_title": (
            "⚡ <b>Инструменты</b>\n\n"
            "Посетите наш магазин AliExpress:\n\n"
            "👇 Нажмите для перехода"
        ),
        "wholesale_prompt": (
            "📦 <b>Оптовый заказ</b>\n\n"
            "Введите <b>количество и модель</b>:\n\n"
            "(Отправьте текст, например:\n"
            "<i>DP9 Тепловизор × 20шт</i>)"
        ),
        "transfer_success": (
            "✅ Ваш запрос передан менеджеру.\n\n"
            "Менеджер ответит в рабочее время."
        ),
        "transfer_fail": "⚠️ Ошибка, попробуйте позже.",
        "wholesale_sent": (
            "✅ Ваш заказ отправлен!\n\n"
            "📝 <b>Сообщение:</b>\n<i>{message}</i>\n\n"
            "Менеджер ответит в рабочее время."
        ),
        "wholesale_cancel": "❌ Заказ отменён.",
        "agent_notify": (
            "📦 <b>Заказ — {category}</b>\n\n"
            "👤 Пользователь: {user_name} (ID: <code>{user_id}</code>)\n"
            "📂 Категория: {category}\n"
        ),
        "agent_wholesale_notify": (
            "📦 <b>Оптовый заказ</b>\n\n"
            "👤 Пользователь: {user_name} (ID: <code>{user_id}</code>)\n"
            "📝 Сообщение: <i>{message}</i>\n"
        ),
        "shop_btn": "🛒 AliExpress",
        "nav_back_type": "◀️ Назад",
        "nav_home": "🏠 Главное меню",
    },
}

# 子分类 → 显示名称
SUB_NAMES = {
    "zh": {"industrial": "工业热成像仪", "hunting": "狩猎热成像仪", "special": "特殊热成像仪"},
    "en": {"industrial": "Industrial Thermal", "hunting": "Hunting Thermal", "special": "Special Thermal"},
    "ru": {"industrial": "Промышленные", "hunting": "Охота", "special": "Специальные"},
}


def t(lang: str, key: str) -> str:
    """获取多语言文案."""
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"][key])


def _user_display(from_user) -> str:  # type: ignore[no-untyped-def]
    """构建用户名展示."""
    parts = []
    if from_user.first_name:
        parts.append(from_user.first_name)
    if from_user.last_name:
        parts.append(from_user.last_name)
    name = " ".join(parts) or "Unknown"
    if from_user.username:
        name += f" (@{from_user.username})"
    return name


def _home_keyboard(lang: str) -> InlineKeyboardBuilder:
    """返回主菜单按钮."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t(lang, "nav_home"),
        callback_data=NavCallback(action="home").pack(),
    ))
    return builder


# ── 回调处理 ────────────────────────────────────────────

@router.callback_query(OrderCallback.filter())
async def on_order_action(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """处理售中下单所有回调."""
    if not callback.message:
        return

    action = callback_data.action

    if action == "category":
        await _on_category(callback, callback_data, lang)
    elif action == "aliexpress":
        await _on_aliexpress(callback, lang)
    elif action == "wholesale":
        await _on_wholesale_start(callback, lang, state)
    elif action == "transfer":
        await _on_transfer(callback, callback_data, lang)
    else:
        await callback.answer()
        return

    await callback.answer()


# ── 热成像仪 → 选子类 ──────────────────────────────────

async def _on_category(
    callback: CallbackQuery, data: OrderCallback, lang: str,
) -> None:
    """产品类型 → 热成像仪子分类 / 返回产品类型."""
    if data.cat_id == "back":
        # 返回产品类型选择
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "type_title"),
            reply_markup=order_product_type_keyboard(lang),
        )
        return

    if data.cat_id == "thermal":
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "thermal_sub_title"),
            reply_markup=order_thermal_subcategory_keyboard(lang),
        )


# ── 动力工具 → 速卖通 ──────────────────────────────────

async def _on_aliexpress(callback: CallbackQuery, lang: str) -> None:
    """动力工具 → 跳转速卖通店铺."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t(lang, "shop_btn"),
        url=settings.aliexpress_store_url,
    ))
    builder.row(InlineKeyboardButton(
        text=t(lang, "nav_back_type"),
        callback_data=OrderCallback(action="category", cat_id="back").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t(lang, "nav_home"),
        callback_data=NavCallback(action="home").pack(),
    ))
    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "aliexpress_title"),
        reply_markup=builder.as_markup(),
    )


# ── 批发订单 → FSM 等待留言 ────────────────────────────

async def _on_wholesale_start(
    callback: CallbackQuery, lang: str, state: FSMContext | None,
) -> None:
    """批发订单 → 进入 FSM 等待用户输入."""
    if state:
        await state.set_state(OrderStates.awaiting_message)
        await state.update_data(lang=lang)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t(lang, "nav_back_type"),
        callback_data=OrderCallback(action="category", cat_id="back").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t(lang, "nav_home"),
        callback_data=NavCallback(action="home").pack(),
    ))
    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "wholesale_prompt"),
        reply_markup=builder.as_markup(),
    )


# ── 热成像仪子分类 → 转特定人工 ────────────────────────

async def _on_transfer(
    callback: CallbackQuery, data: OrderCallback, lang: str,
) -> None:
    """热成像仪子分类点击 → 通知对应客服."""
    sub = data.sub
    from_user = callback.from_user

    # 根据子分类决定转接对象
    if sub == "industrial":
        agent_id = settings.order_agent_1_id
    else:
        # hunting / special → 特定人工 2
        agent_id = settings.order_agent_2_id

    sub_name = SUB_NAMES.get(lang, SUB_NAMES["zh"]).get(sub, sub)

    # 向客服发送通知
    notify_text = t(lang, "agent_notify").format(
        category=sub_name,
        user_name=_user_display(from_user),
        user_id=from_user.id,
    )
    result = await notification_service.notify_agent(agent_id, notify_text)

    # 向用户反馈
    kb = _home_keyboard(lang)
    if result:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "transfer_success"),
            reply_markup=kb.as_markup(),
        )
        logger.info("Order transfer: user=%s sub=%s → agent=%s", from_user.id, sub, agent_id)
    else:
        await callback.message.edit_text(  # type: ignore[union-attr]
            t(lang, "transfer_fail"),
            reply_markup=kb.as_markup(),
        )
        logger.warning("Order transfer failed: user=%s sub=%s agent=%s", from_user.id, sub, agent_id)


# ── FSM: 接收批发订单留言 ──────────────────────────────

@router.message(OrderStates.awaiting_message, F.text)
async def on_wholesale_message(
    message: Message,
    state: FSMContext,
    lang: str = "zh",
) -> None:
    """收到用户的批发订单文本留言 → 转发到客服群组."""
    user_text = message.text or ""
    from_user = message.from_user

    if not from_user:
        return

    # 获取 FSM 中保存的语言
    fsm_data = await state.get_data()
    lang = fsm_data.get("lang", lang)

    # 清除 FSM 状态
    await state.clear()

    # 1. 构建通知文本
    notify_text = t(lang, "agent_wholesale_notify").format(
        user_name=_user_display(from_user),
        user_id=from_user.id,
        message=user_text,
    )

    # 2. 发送到客服群组
    result = await notification_service.notify_support_group(notify_text)

    # 3. 也转发原始消息
    if message.chat and message.message_id:
        await notification_service.forward_to_support(
            chat_id=message.chat.id,
            message_id=message.message_id,
        )

    # 4. 回复用户
    from bot.keyboards.inline import main_menu_keyboard

    if result:
        await message.answer(
            t(lang, "wholesale_sent").format(message=user_text),
            reply_markup=main_menu_keyboard(lang),
        )
        logger.info("Wholesale order from user=%s: %s", from_user.id, user_text[:100])
    else:
        # 即使通知群组失败，也给用户友好提示
        await message.answer(
            t(lang, "wholesale_sent").format(message=user_text),
            reply_markup=main_menu_keyboard(lang),
        )
        logger.warning("Wholesale notification failed for user=%s", from_user.id)
