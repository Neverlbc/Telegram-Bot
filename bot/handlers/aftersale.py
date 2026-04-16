"""售后支持 — 入口菜单 + 订单状态查询."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import AftersaleCallback
from bot.keyboards.inline import (
    aftersale_menu_keyboard,
    device_menu_keyboard,
    logistics_origin_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="aftersale")

AFTERSALE_TITLES = {
    "zh": "🔧 售后支持\n\n请选择服务类型：",
    "en": "🔧 After-sale Support\n\nSelect service type:",
    "ru": "🔧 Послепродажная поддержка\n\nВыберите тип:",
}

ORDER_QUERY_TITLES = {
    "zh": "📋 订单状态查询\n\n请输入您的订单号：\n（直接发送文字消息）",
    "en": "📋 Order Status\n\nPlease enter your order ID:\n(Send text message)",
    "ru": "📋 Статус заказа\n\nВведите номер заказа:\n(Отправьте текст)",
}

LOGISTICS_TITLES = {
    "zh": "🚛 物流查询\n\n请选择发货地：",
    "en": "🚛 Logistics Tracking\n\nSelect origin:",
    "ru": "🚛 Отслеживание\n\nВыберите место отправки:",
}

DEVICE_TITLES = {
    "zh": "🔧 设备支持\n\n请选择：",
    "en": "🔧 Device Support\n\nPlease select:",
    "ru": "🔧 Устройства\n\nВыберите:",
}


@router.callback_query(AftersaleCallback.filter())
async def on_aftersale_action(
    callback: CallbackQuery,
    callback_data: AftersaleCallback,
    lang: str = "zh",
) -> None:
    """处理售后支持操作."""
    if not callback.message:
        return

    action = callback_data.action

    if action == "menu":
        await callback.message.edit_text(
            AFTERSALE_TITLES.get(lang, AFTERSALE_TITLES["zh"]),
            reply_markup=aftersale_menu_keyboard(lang),
        )

    elif action == "order_status":
        # TODO: M5a — 进入 FSM 等待订单号输入
        from bot.states.logistics import AftersaleStates
        # 暂时显示文案，完整实现在 M5a
        await callback.message.edit_text(
            ORDER_QUERY_TITLES.get(lang, ORDER_QUERY_TITLES["zh"]),
        )

    elif action == "logistics":
        await callback.message.edit_text(
            LOGISTICS_TITLES.get(lang, LOGISTICS_TITLES["zh"]),
            reply_markup=logistics_origin_keyboard(lang),
        )

    elif action == "device":
        await callback.message.edit_text(
            DEVICE_TITLES.get(lang, DEVICE_TITLES["zh"]),
            reply_markup=device_menu_keyboard(lang),
        )

    await callback.answer()
