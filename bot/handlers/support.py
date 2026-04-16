"""客服合作 — 商务合作 / 批发咨询 / 转接人工."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import SupportCallback

logger = logging.getLogger(__name__)
router = Router(name="support")


@router.callback_query(SupportCallback.filter())
async def on_support_action(
    callback: CallbackQuery,
    callback_data: SupportCallback,
    lang: str = "zh",
) -> None:
    """处理客服合作操作 — 骨架实现，待 M6 完善."""
    if not callback.message:
        return

    # TODO: M6 模块完善
    placeholder = {
        "zh": "🚧 功能开发中，敬请期待...",
        "en": "🚧 Coming soon...",
        "ru": "🚧 В разработке...",
    }
    await callback.answer(placeholder.get(lang, placeholder["zh"]), show_alert=True)
