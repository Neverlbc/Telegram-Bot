"""Short-lived hidden menu access sessions stored in FSM data."""

from __future__ import annotations

import time
from typing import Any

from aiogram.fsm.context import FSMContext

ACCESS_TTL_SECONDS = 600
DATA_KEY = "_hidden_access"

MENU_VIP_INVENTORY = "vip_inventory"
MENU_SVIP_INVENTORY = "svip_inventory"
MENU_VVIP_INVENTORY = "vvip_inventory"
MENU_SERVICE_ADMIN = "service_admin"
MENU_VANDYCH = "vandych"


def _now() -> int:
    return int(time.time())


def _access_data(data: dict[str, Any]) -> dict[str, int]:
    raw = data.get(DATA_KEY)
    if not isinstance(raw, dict):
        return {}
    result: dict[str, int] = {}
    for key, value in raw.items():
        try:
            result[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return result


async def grant_hidden_access(state: FSMContext, menu: str) -> None:
    data = await state.get_data()
    access = _access_data(data)
    access[menu] = _now() + ACCESS_TTL_SECONDS
    await state.update_data(**{DATA_KEY: access})


async def has_hidden_access(state: FSMContext, menu: str) -> bool:
    data = await state.get_data()
    access = _access_data(data)
    expires_at = access.get(menu, 0)
    if expires_at > _now():
        return True
    if menu in access:
        access.pop(menu, None)
        await state.update_data(**{DATA_KEY: access})
    return False


async def clear_state_keep_hidden_access(state: FSMContext) -> None:
    data = await state.get_data()
    access = _access_data(data)
    await state.clear()
    if access:
        await state.update_data(**{DATA_KEY: access})
