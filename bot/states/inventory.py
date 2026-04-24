"""FSM 状态 — 莫斯科现货查询."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class InventoryStates(StatesGroup):
    pass  # VIP 入口已改为直接发文本密码触发，无需 FSM 状态
