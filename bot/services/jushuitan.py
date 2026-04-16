"""聚水潭 ERP API 对接服务 — 骨架."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OrderInfo:
    """聚水潭订单信息."""

    order_id: str
    status: str  # shipped / unshipped / processing
    shipped_at: str | None = None
    tracking_no: str | None = None
    carrier: str | None = None


class JushuitanService:
    """聚水潭 ERP 对接.

    封装 OAuth2 授权、订单查询等操作。
    Token 缓存在 Redis 中。

    TODO: M5a — 完善实现
    """

    def __init__(self) -> None:
        self.app_key = settings.jushuitan_app_key
        self.app_secret = settings.jushuitan_app_secret
        self._token: str | None = None

    async def get_access_token(self) -> str:
        """获取聚水潭 API access_token.

        TODO: 实现 OAuth2 授权流程 + Redis 缓存
        """
        raise NotImplementedError("聚水潭 OAuth2 授权尚未实现")

    async def query_order(self, order_id: str) -> OrderInfo | None:
        """查询订单发货状态.

        Args:
            order_id: 聚水潭订单号.

        Returns:
            OrderInfo 或 None（未找到）.

        TODO: M5a — 完善 API 调用
        """
        raise NotImplementedError("聚水潭订单查询尚未实现")


# 全局服务实例
jushuitan_service = JushuitanService()
