"""FSM 状态 — 莫斯科现货查询."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class InventoryStates(StatesGroup):
    awaiting_vip_password = State()
