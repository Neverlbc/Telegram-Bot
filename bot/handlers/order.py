"""售中下单 — 批发订单."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import OrderCallback

logger = logging.getLogger(__name__)
router = Router(name="order")


@router.callback_query(OrderCallback.filter())
async def on_order_action(
    callback: CallbackQuery,
    callback_data: OrderCallback,
    lang: str = "zh",
) -> None:
    """处理售中下单操作 — 骨架实现，待 M4 完善."""
    if not callback.message:
        return

    # TODO: M4 模块完善
    placeholder = {
        "zh": "🚧 功能开发中，敬请期待...",
        "en": "🚧 Coming soon...",
        "ru": "🚧 В разработке...",
    }
    await callback.answer(placeholder.get(lang, placeholder["zh"]), show_alert=True)
