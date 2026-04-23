"""FSM 状态 — Vandych VIP 隐藏菜单."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class VipStates(StatesGroup):
    awaiting_wholesale_input = State()
