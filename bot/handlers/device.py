"""设备支持 Handler — 序列号查询 / 设备问题 / 更多选项."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import DeviceCallback

logger = logging.getLogger(__name__)
router = Router(name="device")


@router.callback_query(DeviceCallback.filter())
async def on_device_action(
    callback: CallbackQuery,
    callback_data: DeviceCallback,
    lang: str = "zh",
) -> None:
    """处理设备支持操作 — 骨架实现，待 M5c 完善."""
    if not callback.message:
        return

    # TODO: M5c 模块完善
    placeholder = {
        "zh": "🚧 功能开发中，敬请期待...",
        "en": "🚧 Coming soon...",
        "ru": "🚧 В разработке...",
    }
    await callback.answer(placeholder.get(lang, placeholder["zh"]), show_alert=True)
