"""主菜单导航 — 处理菜单按钮点击和全局导航."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.callbacks import MenuCallback, NavCallback
from bot.keyboards.inline import (
    aftersale_menu_keyboard,
    main_menu_keyboard,
    presale_menu_keyboard,
    support_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="menu")

MENU_TITLES = {
    "zh": "📌 主菜单\n\n请选择您需要的服务：",
    "en": "📌 Main Menu\n\nPlease select a service:",
    "ru": "📌 Главное меню\n\nВыберите услугу:",
}

PRESALE_TITLES = {
    "zh": "🛍 售前咨询\n\n请选择：",
    "en": "🛍 Pre-sale Consultation\n\nPlease select:",
    "ru": "🛍 Консультация\n\nВыберите:",
}

AFTERSALE_TITLES = {
    "zh": "🔧 售后支持\n\n请选择服务类型：",
    "en": "🔧 After-sale Support\n\nSelect service type:",
    "ru": "🔧 Послепродажная поддержка\n\nВыберите тип:",
}

SUPPORT_TITLES = {
    "zh": "💬 客服与合作\n\n请选择：",
    "en": "💬 Support & Cooperation\n\nPlease select:",
    "ru": "💬 Поддержка\n\nВыберите:",
}

SETTINGS_TITLES = {
    "zh": "⚙️ 设置\n\n请选择语言：",
    "en": "⚙️ Settings\n\nSelect language:",
    "ru": "⚙️ Настройки\n\nВыберите язык:",
}

ORDER_TITLES = {
    "zh": "📦 售中下单\n\n请输入您需要的商品数量和型号：\n\n（直接发送文字消息即可）",
    "en": "📦 Place Order\n\nPlease enter product quantity and model:\n\n(Send text message directly)",
    "ru": "📦 Заказ\n\nВведите количество и модель:\n\n(Отправьте текстовое сообщение)",
}


@router.message(Command("menu"))
async def on_menu_command(message: Message, lang: str = "zh", state: FSMContext | None = None) -> None:
    """处理 /menu 命令 — 返回主菜单."""
    if state:
        await state.clear()
    await message.answer(
        MENU_TITLES.get(lang, MENU_TITLES["zh"]),
        reply_markup=main_menu_keyboard(lang),
    )


@router.message(Command("cancel"))
async def on_cancel_command(message: Message, lang: str = "zh", state: FSMContext | None = None) -> None:
    """处理 /cancel 命令 — 清除 FSM 状态，回主菜单."""
    if state:
        await state.clear()

    texts = {
        "zh": "❌ 已取消当前操作。",
        "en": "❌ Operation cancelled.",
        "ru": "❌ Операция отменена.",
    }
    await message.answer(texts.get(lang, texts["zh"]))
    await message.answer(
        MENU_TITLES.get(lang, MENU_TITLES["zh"]),
        reply_markup=main_menu_keyboard(lang),
    )


@router.callback_query(MenuCallback.filter())
async def on_menu_action(
    callback: CallbackQuery,
    callback_data: MenuCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """处理主菜单按钮点击."""
    if not callback.message:
        return

    action = callback_data.action

    if action == "presale":
        await callback.message.edit_text(
            PRESALE_TITLES.get(lang, PRESALE_TITLES["zh"]),
            reply_markup=presale_menu_keyboard(lang),
        )
    elif action == "order":
        # 进入批发下单 FSM
        from bot.states.order import OrderStates

        if state:
            await state.set_state(OrderStates.awaiting_message)
        await callback.message.edit_text(
            ORDER_TITLES.get(lang, ORDER_TITLES["zh"]),
        )
    elif action == "aftersale":
        await callback.message.edit_text(
            AFTERSALE_TITLES.get(lang, AFTERSALE_TITLES["zh"]),
            reply_markup=aftersale_menu_keyboard(lang),
        )
    elif action == "support":
        await callback.message.edit_text(
            SUPPORT_TITLES.get(lang, SUPPORT_TITLES["zh"]),
            reply_markup=support_keyboard(lang),
        )
    elif action == "settings":
        from bot.keyboards.inline import settings_menu_keyboard

        await callback.message.edit_text(
            SETTINGS_TITLES.get(lang, SETTINGS_TITLES["zh"]),
            reply_markup=settings_menu_keyboard(lang),
        )
    elif action == "setting_lang":
        from bot.keyboards.inline import language_keyboard

        await callback.message.edit_text(
            "🌐 " + SETTINGS_TITLES.get(lang, SETTINGS_TITLES["zh"]),
            reply_markup=language_keyboard(),
        )

    await callback.answer()


@router.callback_query(NavCallback.filter(F.action == "home"))
async def on_nav_home(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """处理「返回主菜单」按钮."""
    if not callback.message:
        return
    if state:
        await state.clear()
    await callback.message.edit_text(
        MENU_TITLES.get(lang, MENU_TITLES["zh"]),
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(NavCallback.filter(F.action == "back"))
async def on_nav_back(
    callback: CallbackQuery,
    callback_data: NavCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """处理「返回上级菜单」按钮."""
    if not callback.message:
        return
    if state:
        await state.clear()

    target = callback_data.target

    if target == "menu" or not target:
        await callback.message.edit_text(
            MENU_TITLES.get(lang, MENU_TITLES["zh"]),
            reply_markup=main_menu_keyboard(lang),
        )
    elif target == "presale":
        await callback.message.edit_text(
            PRESALE_TITLES.get(lang, PRESALE_TITLES["zh"]),
            reply_markup=presale_menu_keyboard(lang),
        )
    elif target == "aftersale":
        await callback.message.edit_text(
            AFTERSALE_TITLES.get(lang, AFTERSALE_TITLES["zh"]),
            reply_markup=aftersale_menu_keyboard(lang),
        )
    elif target == "support":
        await callback.message.edit_text(
            SUPPORT_TITLES.get(lang, SUPPORT_TITLES["zh"]),
            reply_markup=support_keyboard(lang),
        )
    elif target == "settings":
        from bot.keyboards.inline import settings_menu_keyboard

        await callback.message.edit_text(
            SETTINGS_TITLES.get(lang, SETTINGS_TITLES["zh"]),
            reply_markup=settings_menu_keyboard(lang),
        )
    else:
        # 默认回主菜单
        await callback.message.edit_text(
            MENU_TITLES.get(lang, MENU_TITLES["zh"]),
            reply_markup=main_menu_keyboard(lang),
        )

    await callback.answer()
