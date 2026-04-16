"""用户设置与个人中心."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards.callbacks import MenuCallback, NavCallback
from bot.keyboards.inline import language_keyboard, settings_menu_keyboard
from bot.models.user import User

logger = logging.getLogger(__name__)
router = Router(name="settings")


@router.message(Command("lang"))
async def on_lang_command(message: Message, lang: str = "zh") -> None:
    """处理 /lang 命令 — 快捷切换语言."""
    texts = {
        "zh": "🌐 请选择新的语言：",
        "en": "🌐 Select language:",
        "ru": "🌐 Выберите язык:",
    }
    await message.answer(
        texts.get(lang, texts["zh"]),
        reply_markup=language_keyboard(),
    )


@router.message(Command("help"))
async def on_help_command(message: Message, lang: str = "zh") -> None:
    """处理 /help 命令."""
    help_texts = {
        "zh": (
            "📖 帮助信息\n\n"
            "/start — 启动机器人\n"
            "/menu — 返回主菜单\n"
            "/lang — 切换语言\n"
            "/track — 快捷物流查询\n"
            "/support — 联系客服\n"
            "/cancel — 取消当前操作\n"
            "/help — 显示此帮助"
        ),
        "en": (
            "📖 Help\n\n"
            "/start — Start bot\n"
            "/menu — Main menu\n"
            "/lang — Change language\n"
            "/track — Track shipment\n"
            "/support — Contact support\n"
            "/cancel — Cancel operation\n"
            "/help — Show this help"
        ),
        "ru": (
            "📖 Помощь\n\n"
            "/start — Запуск бота\n"
            "/menu — Главное меню\n"
            "/lang — Сменить язык\n"
            "/track — Отслеживание\n"
            "/support — Поддержка\n"
            "/cancel — Отмена\n"
            "/help — Показать помощь"
        ),
    }
    await message.answer(help_texts.get(lang, help_texts["zh"]))


@router.callback_query(MenuCallback.filter(F.action == "profile"))
async def on_profile_action(
    callback: CallbackQuery,
    lang: str = "zh",
    current_user: User | None = None,
) -> None:
    """显示用户个人面板."""
    if not callback.message:
        return

    profile_text = ""
    if current_user:
        uid = current_user.telegram_id
        uname = f"@{current_user.username}" if current_user.username else "-"
        # TODO: 从数据库里聚合用户的统计数据，比如查询订单数量，工单数量等
        joined_at = current_user.created_at.strftime("%Y-%m-%d") if current_user.created_at else "未知"
        
        roles = {
            "zh": "普通用户", 
            "en": "Standard User", 
            "ru": "Пользователь"
        }
        # 如果你后续加上了 is_admin 等字段，这里的角色展示会变化
        role_label = roles.get(lang, roles["zh"])
        
        texts = {
            "zh": f"👤 **个人中心**\n\n🆔 User ID: `{uid}`\n📝 Username: {uname}\n🌟 角色: {role_label}\n📅 注册日期: {joined_at}\n\n📊 **数据概览** (开发中):\n- 历史订单数: 0\n- 活跃服务单: 0",
            "en": f"👤 **Personal Center**\n\n🆔 User ID: `{uid}`\n📝 Username: {uname}\n🌟 Role: {role_label}\n📅 Joined: {joined_at}\n\n📊 **Overview** (WIP):\n- Total Orders: 0\n- Active Tickets: 0",
            "ru": f"👤 **Личный кабинет**\n\n🆔 User ID: `{uid}`\n📝 Username: {uname}\n🌟 Роль: {role_label}\n📅 Регистрация: {joined_at}\n\n📊 **Обзор** (WIP):\n- Ваши заказы: 0\n- Активные тикеты: 0"
        }
        profile_text = texts.get(lang, texts["zh"])
    else:
        # 当没有数据库连接跑在内存模式时的展示
        uid = callback.from_user.id
        texts = {
            "zh": f"👤 **个人中心**\n\n🆔 User ID: `{uid}`\n\n(数据库未连接，无法拉取详细数据)",
            "en": f"👤 **Personal Center**\n\n🆔 User ID: `{uid}`\n\n(DB not connected)",
            "ru": f"👤 **Личный кабинет**\n\n🆔 User ID: `{uid}`\n\n(БД не подключена)"
        }
        profile_text = texts.get(lang, texts["zh"])

    await callback.message.edit_text(
        profile_text,
        # 调用专门包含 "返回设置" 和 "返回首页" 的按钮构造器
        reply_markup=settings_menu_keyboard(lang, show_profile=False),
        parse_mode="Markdown"
    )
    await callback.answer()
