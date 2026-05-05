"""聚水潭 ERP API 对接服务.

签名算法（来自 other/jushuitan_base_client.py）：
  sign = MD5(app_secret + key1val1key2val2...).hexdigest()  ← 小写，无尾部 secret

请求格式：form data，业务参数放在 biz 字段（JSON 字符串）。

Token 管理：
  - access_token 有效期 2 小时 (expires_in=7200)
  - 过期前 5 分钟自动 refresh_token 刷新
  - token 缓存在 Redis；Redis 不可用时退化为内存缓存
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)

# Token 提前刷新阈值（秒）
_TOKEN_REFRESH_BUFFER = 300  # 过期前 5 分钟刷新

# 内存 fallback（Redis 不可用时）
_mem_token: dict[str, Any] = {}


@dataclass
class OrderInfo:
    """聚水潭订单信息 (M5a 占位)."""

    order_id: str
    status: str
    shipped_at: str | None = None
    tracking_no: str | None = None
    carrier: str | None = None


class JushuitanClient:
    """聚水潭 ERP API 客户端（异步版）."""

    def __init__(self) -> None:
        self.app_key = settings.jushuitan_app_key
        self.app_secret = settings.jushuitan_app_secret
        self.base_url = settings.jushuitan_api_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    # ── 签名 ──────────────────────────────────────────────

    def _sign(self, params: dict[str, Any]) -> str:
        """生成聚水潭签名（与 other/jushuitan_base_client.py 完全一致）."""
        filtered = {k: v for k, v in params.items() if k != "sign"}
        sorted_kv = "".join(f"{k}{v}" for k, v in sorted(filtered.items()))
        raw = f"{self.app_secret}{sorted_kv}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    # ── Token 管理 ────────────────────────────────────────

    async def _redis(self) -> Any:
        """返回 Redis 客户端，不可用返回 None."""
        try:
            from bot.services.sheets import get_redis_client
            return get_redis_client()
        except Exception:
            return None

    async def _load_token(self) -> dict[str, Any] | None:
        """从 Redis 或内存缓存加载 token 信息."""
        redis = await self._redis()
        if redis:
            try:
                raw = await redis.get("jst:token")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return _mem_token.get("token")

    async def _save_token(self, token_data: dict[str, Any]) -> None:
        """保存 token 信息到 Redis 和内存缓存."""
        _mem_token["token"] = token_data
        redis = await self._redis()
        if redis:
            try:
                ttl = token_data.get("expires_in", 7200)
                await redis.set("jst:token", json.dumps(token_data), ex=ttl)
            except Exception:
                pass

    async def _fetch_token(self) -> dict[str, Any]:
        """从聚水潭获取初始 access_token."""
        import random, string
        code = "".join(random.choices(string.ascii_letters + string.digits, k=6))
        params: dict[str, Any] = {
            "app_key": self.app_key,
            "timestamp": str(int(time.time())),
            "grant_type": "authorization_code",
            "charset": "utf-8",
            "code": code,
        }
        params["sign"] = self._sign(params)

        url = f"{self.base_url}/openWeb/auth/getInitToken"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    async def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """用 refresh_token 刷新 access_token."""
        params: dict[str, Any] = {
            "app_key": self.app_key,
            "timestamp": str(int(time.time())),
            "grant_type": "refresh_token",
            "charset": "utf-8",
            "refresh_token": refresh_token,
        }
        params["sign"] = self._sign(params)

        url = f"{self.base_url}/openWeb/auth/getInitToken"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    async def get_access_token(self) -> str | None:
        """获取有效的 access_token，自动刷新过期 token."""
        cached = await self._load_token()

        if cached:
            expires_at = cached.get("expires_at", 0)
            if time.time() < expires_at - _TOKEN_REFRESH_BUFFER:
                return cached.get("access_token")

            # 尝试用 refresh_token 刷新
            refresh_token = cached.get("refresh_token")
            if refresh_token:
                try:
                    result = await self._refresh_token(refresh_token)
                    if result.get("code") == 0:
                        data = result["data"]
                        data["expires_at"] = time.time() + data.get("expires_in", 7200)
                        await self._save_token(data)
                        logger.info("[JST] access_token 已刷新")
                        return data["access_token"]
                except Exception as e:
                    logger.warning("[JST] token 刷新失败，尝试重新获取: %s", e)

        # 重新获取 token
        try:
            result = await self._fetch_token()
            if result.get("code") == 0:
                data = result["data"]
                data["expires_at"] = time.time() + data.get("expires_in", 7200)
                await self._save_token(data)
                logger.info("[JST] access_token 已获取")
                return data["access_token"]
            else:
                logger.error("[JST] 获取 token 失败: %s", result)
        except Exception as e:
            logger.error("[JST] 获取 token 异常: %s", e)

        return None

    # ── HTTP 请求 ─────────────────────────────────────────

    async def _post(self, path: str, biz_params: dict[str, Any]) -> dict[str, Any]:
        """签名后以 form data 方式发送请求，业务参数放在 biz 字段."""
        if not self.is_configured:
            logger.warning("[JST] 未配置聚水潭参数，跳过: %s", path)
            return {}

        access_token = await self.get_access_token()
        if not access_token:
            logger.error("[JST] 无法获取 access_token，跳过: %s", path)
            return {}

        biz_json = json.dumps(biz_params, ensure_ascii=False, separators=(",", ":"))
        form: dict[str, Any] = {
            "app_key": self.app_key,
            "access_token": access_token,
            "timestamp": str(int(time.time())),
            "charset": "utf-8",
            "version": "2",
            "biz": biz_json,
        }
        form["sign"] = self._sign(form)

        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    resp.raise_for_status()
                    result = await resp.json(content_type=None)
                    code = result.get("code")
                    if str(code) != "0":
                        logger.error("[JST] 业务异常 %s -> code=%s msg=%s", path, code, result.get("msg"))
                    return result
        except aiohttp.ClientResponseError as e:
            logger.error("[JST] HTTP %s: %s -> %s", e.status, path, e.message)
        except Exception as e:
            logger.error("[JST] 请求失败: %s -> %s", path, e)
        return {}

    # ── 库存查询 ──────────────────────────────────────────

    async def get_stock_map(
        self,
        sku_ids: list[str],
        warehouse_code: str = "",
    ) -> dict[str, int]:
        """批量查询 SKU 的订单占有数，返回 {sku_id: order_lock}.

        - warehouse_code: 只统计该仓库编号的 order_lock（空字符串 = 汇总所有仓）
        - 自动分批（每批 ≤ 100 个 SKU）
        - 自动翻页直到 has_next=False
        """
        if not sku_ids or not self.is_configured:
            return {}

        stock_map: dict[str, int] = {}

        for i in range(0, len(sku_ids), 100):
            batch = sku_ids[i : i + 100]
            page = 1
            while True:
                result = await self._post(
                    "/open/inventory/query",
                    {
                        "sku_ids": ",".join(batch),
                        "page_index": page,
                        "page_size": 100,
                    },
                )
                data = result.get("data") or {}
                for item in data.get("inventorys") or []:
                    sku = str(item.get("sku_id", "")).strip()
                    if not sku:
                        continue
                    # 若配置了仓库编号，只统计该仓库的 order_lock
                    if warehouse_code:
                        item_wh = (
                            str(item.get("i_ware_code", "") or item.get("storekeeper_code", "")).strip()
                        )
                        if item_wh and item_wh != warehouse_code:
                            continue
                    # 跨仓库累加，不覆盖（防止多行同 SKU 时只保留最后一行）
                    stock_map[sku] = stock_map.get(sku, 0) + int(item.get("order_lock", 0))
                if not data.get("has_next", False):
                    break
                page += 1

        return stock_map

    # ── 订单查询（M5a）────────────────────────────────────

    async def query_order_by_so_id(self, so_id: str) -> dict[str, Any]:
        """通过线上单号（用户填写的订单号）查询订单状态.

        Returns raw API data dict, or {} on failure.
        """
        return await self._post(
            "/open/orders/single/query",
            {
                "so_ids": [so_id],
                "page_index": 1,
                "page_size": 10,
                "is_get_total": False,
            },
        )

    async def query_order(self, order_id: str) -> OrderInfo | None:
        """查询订单发货状态，返回 OrderInfo 或 None（M5a 主入口）."""
        result = await self.query_order_by_so_id(order_id)
        orders = (result.get("data") or {}).get("orders") or []
        if not orders:
            return None

        o = orders[0]
        # 聚水潭订单状态: WaitConfirm/WaitPay/WaitSend/Sended/ConsignedConfirmed/Cancelled 等
        status_raw = o.get("status", "")
        shipped = status_raw in ("Sended", "ConsignedConfirmed")
        tracking_no = None
        carrier = None

        logistics = o.get("logistics") or []
        if logistics:
            tracking_no = logistics[0].get("l_id")
            carrier = logistics[0].get("logistics_company")

        return OrderInfo(
            order_id=order_id,
            status="shipped" if shipped else "unshipped",
            shipped_at=o.get("send_date"),
            tracking_no=tracking_no,
            carrier=carrier,
        )


# 全局实例
jushuitan_client = JushuitanClient()
