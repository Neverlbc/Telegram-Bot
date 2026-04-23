"""物流查询服务 — 策略模式适配多物流商."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TrackingEvent:
    """物流轨迹事件."""

    time: str
    description: str
    location: str = ""


@dataclass
class TrackingResult:
    """物流查询结果."""

    tracking_no: str
    carrier: str
    status: str  # in_transit / delivered / exception / not_found
    events: list[TrackingEvent] = field(default_factory=list)
    tracking_url: str = ""


class LogisticsTracker(ABC):
    """物流查询抽象基类."""

    @abstractmethod
    async def query_by_tracking_number(self, tracking_no: str) -> TrackingResult:
        """根据跟踪号查询物流轨迹."""

    @abstractmethod
    def get_tracking_url(self, tracking_no: str) -> str:
        """获取物流商的在线查询 URL."""


class CDEKTracker(LogisticsTracker):
    """CDEK 快递查询.

    TODO: M5b — 完善 CDEK API 集成
    """

    async def query_by_tracking_number(self, tracking_no: str) -> TrackingResult:
        raise NotImplementedError("CDEK 查询尚未实现")

    def get_tracking_url(self, tracking_no: str) -> str:
        return f"https://www.cdek.ru/tracking?order_id={tracking_no}"


class RUPostTracker(LogisticsTracker):
    """俄罗斯邮政查询.

    TODO: M5b — 完善 RU Post API 集成
    """

    async def query_by_tracking_number(self, tracking_no: str) -> TrackingResult:
        raise NotImplementedError("RU Post 查询尚未实现")

    def get_tracking_url(self, tracking_no: str) -> str:
        return f"https://www.pochta.ru/tracking#{tracking_no}"


class CainiaoTracker(LogisticsTracker):
    """菜鸟物流查询.

    TODO: M5b — 完善菜鸟 API 集成
    """

    async def query_by_tracking_number(self, tracking_no: str) -> TrackingResult:
        raise NotImplementedError("菜鸟查询尚未实现")

    def get_tracking_url(self, tracking_no: str) -> str:
        return f"https://global.cainiao.com/detail.htm?mailNoList={tracking_no}"


class AirFreightTracker(LogisticsTracker):
    """空运查询.

    TODO: M5b — 完善空运查询实现
    """

    async def query_by_tracking_number(self, tracking_no: str) -> TrackingResult:
        raise NotImplementedError("空运查询尚未实现")

    def get_tracking_url(self, tracking_no: str) -> str:
        return ""


class LogisticsTrackerFactory:
    """物流查询工厂 — 根据物流商类型返回对应的 Tracker."""

    _trackers: dict[str, LogisticsTracker] = {
        "cdek": CDEKTracker(),
        "rupost": RUPostTracker(),
        "cainiao": CainiaoTracker(),
        "airfreight": AirFreightTracker(),
    }

    @classmethod
    def get_tracker(cls, carrier: str) -> LogisticsTracker:
        """获取指定物流商的 Tracker.

        Args:
            carrier: 物流商标识.

        Returns:
            LogisticsTracker 实例.

        Raises:
            ValueError: 不支持的物流商.
        """
        tracker = cls._trackers.get(carrier)
        if not tracker:
            raise ValueError(f"不支持的物流商: {carrier}")
        return tracker
