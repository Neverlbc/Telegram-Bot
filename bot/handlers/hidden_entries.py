"""Global password entries for hidden menus.

These handlers are registered before feature routers so passwords work even
when the user is currently inside a feature FSM prompt.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import settings
from bot.keyboards.inline import inventory_hidden_menu_keyboard, service_center_admin_keyboard, vip_menu_keyboard
from bot.services.hidden_access import (
    MENU_SERVICE_ADMIN,
    MENU_SVIP_INVENTORY,
    MENU_VANDYCH,
    MENU_VIP_INVENTORY,
    MENU_VVIP_INVENTORY,
    grant_hidden_access,
)
from bot.services.inventory_tiers import inventory_tier_label

router = Router(name="hidden_entries")


def _hidden_password_kind(text: str | None) -> str:
    password = (text or "").strip()
    if not password:
        return ""
    if password == settings.vip_inventory_password.strip():
        return MENU_VIP_INVENTORY
    if password == settings.svip_inventory_password.strip():
        return MENU_SVIP_INVENTORY
    if password == settings.vvip_inventory_password.strip():
        return MENU_VVIP_INVENTORY
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

    if kind in {MENU_VIP_INVENTORY, MENU_SVIP_INVENTORY, MENU_VVIP_INVENTORY}:
        from bot.handlers.inventory import _t as inv_t
        tier = {
            MENU_VIP_INVENTORY: "vip",
            MENU_SVIP_INVENTORY: "svip",
            MENU_VVIP_INVENTORY: "vvip",
        }[kind]

        await message.answer(
            inv_t(lang, "hidden_menu_title").format(tier=inventory_tier_label(tier)),
            reply_markup=inventory_hidden_menu_keyboard(lang, tier=tier),
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
