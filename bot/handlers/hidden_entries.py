"""Global password entries for hidden menus.

These handlers are registered before feature routers so passwords work even
when the user is currently inside a feature FSM prompt.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import settings
from bot.keyboards.inline import inventory_category_keyboard, service_center_admin_keyboard, vip_menu_keyboard
from bot.services.hidden_access import (
    MENU_SERVICE_ADMIN,
    MENU_VANDYCH,
    MENU_VIP_INVENTORY,
    grant_hidden_access,
)

router = Router(name="hidden_entries")


def _hidden_password_kind(text: str | None) -> str:
    password = (text or "").strip()
    if not password:
        return ""
    if password == settings.vip_inventory_password.strip():
        return MENU_VIP_INVENTORY
    if password == settings.service_admin_password.strip():
        return MENU_SERVICE_ADMIN
    if password == settings.vandych_password.strip():
        return MENU_VANDYCH
    return ""


@router.message(F.text.func(_hidden_password_kind))
async def on_hidden_password(
    message: Message,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    kind = _hidden_password_kind(message.text)
    if not kind:
        return
    if state:
        await state.clear()
        await grant_hidden_access(state, kind)

    if kind == MENU_VIP_INVENTORY:
        from bot.handlers.inventory import _t as inv_t

        await message.answer(
            inv_t(lang, "vip_category_title"),
            reply_markup=inventory_category_keyboard(lang, vip=True),
        )
    elif kind == MENU_SERVICE_ADMIN:
        from bot.handlers.service_center import _t as sc_t

        await message.answer(
            sc_t(lang, "admin_title"),
            reply_markup=service_center_admin_keyboard(lang),
        )
    elif kind == MENU_VANDYCH:
        from bot.handlers.vip import _t as vip_t

        await message.answer(
            vip_t(lang, "welcome"),
            reply_markup=vip_menu_keyboard(lang),
        )
