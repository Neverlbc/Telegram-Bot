"""物流查询 Handler."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import LogisticsCallback
from bot.keyboards.inline import logistics_carrier_keyboard

logger = logging.getLogger(__name__)
router = Router(name="logistics")


@router.callback_query(LogisticsCallback.filter())
async def on_logistics_action(
    callback: CallbackQuery,
    callback_data: LogisticsCallback,
    lang: str = "zh",
) -> None:
    """处理物流查询操作 — 骨架实现，待 M5b 完善."""
    if not callback.message:
        return

    action = callback_data.action

    if action == "origin":
        origin = callback_data.origin
        if origin == "moscow":
            # 莫斯科发货 → 选择物流商
            titles = {
                "zh": "🇷🇺 莫斯科发货\n\n请选择物流商：",
                "en": "🇷🇺 Moscow Shipping\n\nSelect carrier:",
                "ru": "🇷🇺 Москва\n\nВыберите перевозчика:",
            }
            await callback.message.edit_text(
                titles.get(lang, titles["zh"]),
                reply_markup=logistics_carrier_keyboard(lang),
            )
        elif origin == "china":
            # 中国发货 → 直接输入跟踪号
            # TODO: M5b — 进入 FSM
            titles = {
                "zh": "🇨🇳 中国发货\n\n请输入您的物流跟踪号：\n（直接发送文字消息）",
                "en": "🇨🇳 China Shipping\n\nEnter tracking number:\n(Send text message)",
                "ru": "🇨🇳 Китай\n\nВведите номер отслеживания:\n(Отправьте текст)",
            }
            await callback.message.edit_text(
                titles.get(lang, titles["zh"]),
            )

    elif action == "carrier":
        # 选择了物流商 → 输入跟踪号
        # TODO: M5b — 进入 FSM
        titles = {
            "zh": "请输入您的物流跟踪号：\n（直接发送文字消息）",
            "en": "Enter tracking number:\n(Send text message)",
            "ru": "Введите номер отслеживания:\n(Отправьте текст)",
        }
        await callback.message.edit_text(
            titles.get(lang, titles["zh"]),
        )

    await callback.answer()
