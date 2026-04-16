"""物流查询 & 售后查询 FSM 状态组."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class LogisticsStates(StatesGroup):
    """物流查询流程状态."""

    select_origin = State()        # 选择发货地
    select_carrier = State()       # 选择物流商（仅莫斯科发货）
    awaiting_tracking_no = State()  # 等待用户输入跟踪号


class AftersaleStates(StatesGroup):
    """售后订单查询流程状态."""

    awaiting_order_id = State()  # 等待用户输入订单号


class SerialStates(StatesGroup):
    """序列号查询流程状态."""

    awaiting_serial_no = State()  # 等待用户输入序列号


class DeviceIssueStates(StatesGroup):
    """设备问题提交流程状态."""

    awaiting_content = State()  # 等待用户输入问题详情
