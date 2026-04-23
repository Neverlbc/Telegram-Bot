"""客服合作 — 我是博主 / 我是批发商 / 狩猎俱乐部 → 转人工.

流程（来自设计稿青色部分）：
  需要合作 →
  ├── 我是博主      → 转 @ABFOfficialGroup（预填身份）
  ├── 我是批发商    → 转 @ABFOfficialGroup（预填身份）
  └── 狩猎俱乐部   → 转 @ABFOfficialGroup（预填身份）
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.callbacks import NavCallback, SupportCallback

logger = logging.getLogger(__name__)
router = Router(name="support")


# ── 多语言文案 ──────────────────────────────────────────

TEXTS = {
    "zh": {
        "transfer_title": (
            "🤝 <b>合作咨询 — {role}</b>\n\n"
            "请点击下方按钮联系客服，\n"
            "我们将安排专人与您对接。"
        ),
        "contact_agent": "💬 联系客服 @{username}",
        "nav_home": "🏠 返回主菜单",
    },
    "en": {
        "transfer_title": (
            "🤝 <b>Cooperation — {role}</b>\n\n"
            "Please click below to contact our team.\n"
            "We'll arrange a dedicated contact for you."
        ),
        "contact_agent": "💬 Contact @{username}",
        "nav_home": "🏠 Main Menu",
    },
    "ru": {
        "transfer_title": (
            "🤝 <b>Сотрудничество — {role}</b>\n\n"
            "Нажмите ниже, чтобы связаться с нами.\n"
            "Мы назначим персонального менеджера."
        ),
        "contact_agent": "💬 Написать @{username}",
        "nav_home": "🏠 Главное меню",
    },
}

# 身份类型 → 显示名称
ROLE_NAMES = {
    "zh": {"blogger": "博主", "wholesaler": "批发商", "huntclub": "狩猎俱乐部"},
    "en": {"blogger": "Blogger", "wholesaler": "Wholesaler", "huntclub": "Hunting Club"},
    "ru": {"blogger": "Блогер", "wholesaler": "Оптовик", "huntclub": "Охотничий клуб"},
}

# 身份类型 → 预填消息
PREFILL_MSGS = {
    "zh": {
        "blogger": "你好，我是博主，想咨询合作事宜。",
        "wholesaler": "你好，我是批发商，想咨询批发合作。",
        "huntclub": "你好，我是狩猎俱乐部，想咨询合作。",
    },
    "en": {
        "blogger": "Hi, I'm a blogger interested in cooperation.",
        "wholesaler": "Hi, I'm a wholesaler interested in partnership.",
        "huntclub": "Hi, I'm from a hunting club, interested in cooperation.",
    },
    "ru": {
        "blogger": "Здравствуйте, я блогер, интересует сотрудничество.",
        "wholesaler": "Здравствуйте, я оптовик, интересует партнёрство.",
        "huntclub": "Здравствуйте, охотничий клуб, интересует сотрудничество.",
    },
}


def t(lang: str, key: str) -> str:
    """获取多语言文案."""
    return TEXTS.get(lang, TEXTS["zh"]).get(key, TEXTS["zh"][key])


# ── 回调处理 ────────────────────────────────────────────

@router.callback_query(SupportCallback.filter())
async def on_support_action(
    callback: CallbackQuery,
    callback_data: SupportCallback,
    lang: str = "zh",
) -> None:
    """处理合作咨询 — 全部转 @ABFOfficialGroup."""
    if not callback.message:
        return

    action = callback_data.action
    role_name = ROLE_NAMES.get(lang, ROLE_NAMES["zh"]).get(action, action)
    prefill = PREFILL_MSGS.get(lang, PREFILL_MSGS["zh"]).get(action, "")

    # 构建带预填消息的联系客服链接
    agent_url = f"https://t.me/{settings.human_agent_username}"
    if prefill:
        agent_url += f"?text={quote(prefill)}"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t(lang, "contact_agent").format(username=settings.human_agent_username),
        url=agent_url,
    ))
    builder.row(InlineKeyboardButton(
        text=t(lang, "nav_home"),
        callback_data=NavCallback(action="home").pack(),
    ))

    await callback.message.edit_text(  # type: ignore[union-attr]
        t(lang, "transfer_title").format(role=role_name),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()
    logger.info("Support transfer: user=%s role=%s → @%s", callback.from_user.id, action, settings.human_agent_username)
