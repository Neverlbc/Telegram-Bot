"""批发下单 FSM 状态组."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    """批发下单流程状态."""

    awaiting_message = State()  # 等待用户输入数量和型号
