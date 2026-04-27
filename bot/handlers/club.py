"""A-BF 昼夜俱乐部 — 跳转 TG 社群链接."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import NavCallback

logger = logging.getLogger(__name__)
router = Router(name="club")

TEXTS: dict[str, dict[str, str]] = {
    "zh": {
        "text": "🌙 <b>A-BF昼夜俱乐部</b>\n\n点击下方按钮加入俱乐部交流群：",
        "btn": "🔗 进入俱乐部",
        "not_set": "⚠️ 俱乐部链接暂未配置，请联系管理员。",
    },
    "en": {
        "text": "🌙 <b>A-BF Day and Night Club</b>\n\nClick below to join the club community:",
        "btn": "🔗 Join Club",
        "not_set": "⚠️ Club link not configured yet.",
    },
    "ru": {
        "text": "🌙 <b>A-BF Дневной и ночной клуб</b>\n\nНажмите ниже, чтобы присоединиться к клубному сообществу:",
        "btn": "🔗 Вступить в клуб",
        "not_set": "⚠️ Ссылка на клуб не настроена.",
    },
}


def _t(lang: str, key: str) -> str:
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"][key])


# Club is triggered via main_menu_keyboard's URL button directly (no router needed
# for the click), but we keep this handler for potential future use and for the
# case where club_tg_link is not configured (the menu.py NavCallback "back" lands here).

async def send_club_message(message: Message, lang: str = "zh") -> None:
    """Send club link message (called by menu handler)."""
    link = settings.club_tg_link
    builder = InlineKeyboardBuilder()
    if link and "placeholder" not in link:
        builder.row(InlineKeyboardButton(text=_t(lang, "btn"), url=link))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠"),
        callback_data=NavCallback(action="home").pack(),
    ))
    text = _t(lang, "text") if (link and "placeholder" not in link) else _t(lang, "not_set")
    await message.answer(text, reply_markup=builder.as_markup())
