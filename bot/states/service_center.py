"""FSM 状态 — A-BF 俄罗斯服务中心."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ServiceCenterStates(StatesGroup):
    awaiting_cdek_no = State()
    awaiting_admin_password = State()
    awaiting_sn_query = State()
