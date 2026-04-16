"""售前咨询 — 商品清单 / 配送说明 / 常见问题."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import PresaleCallback

logger = logging.getLogger(__name__)
router = Router(name="presale")


@router.callback_query(PresaleCallback.filter())
async def on_presale_action(
    callback: CallbackQuery,
    callback_data: PresaleCallback,
    lang: str = "zh",
) -> None:
    """处理售前咨询操作 — 骨架实现，待 M3 完善."""
    if not callback.message:
        return

    action = callback_data.action

    # TODO: M3 模块完善具体逻辑
    placeholder = {
        "zh": "🚧 功能开发中，敬请期待...",
        "en": "🚧 Coming soon...",
        "ru": "🚧 В разработке...",
    }

    if action in ("catalog", "delivery", "faq", "category", "product", "variant", "faq_detail"):
        logger.info("Presale action: %s (lang=%s)", action, lang)
        await callback.answer(placeholder.get(lang, placeholder["zh"]), show_alert=True)
    else:
        await callback.answer()
