"""跨运宝 (KYB / Kuayunbao) WMS 接口客户端.

用于对接跨运宝进行可用库存查询、库存调整等操作。
认证方式基于 HTTP 头中的 MD5 签名:
x-app-id: appId
x-app-sign: MD5(appSecret + timestamp + postJson)
x-request-time: timestamp
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)


class KuayunbaoClient:
    """跨运宝 API 客户端."""

    def __init__(self) -> None:
        self.app_id = settings.kyb_app_id
        self.app_secret = settings.kyb_app_secret
        # 支持去除可能携带的尾部斜杠
        self.base_url = settings.kyb_api_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        """检查凭证是否已配置."""
        return bool(self.app_id and self.app_secret)

    def _build_headers(self, request_data: dict[str, Any]) -> dict[str, str]:
        """构建认证签名及 Request Headers."""
        if not self.is_configured:
            raise ValueError("[KYB] 未配置 KYB_APP_ID 或 KYB_APP_SECRET")

        post_json = json.dumps(request_data, ensure_ascii=False, separators=(",", ":"))
        timestamp = str(int(time.time() * 1000))  # 毫秒级时间戳

        # 签名算法: MD5(appSecret + timestamp + postJson)
        sign_data = self.app_secret + timestamp + post_json
        app_sign = hashlib.md5(sign_data.encode("utf-8")).hexdigest()

        return {
            "Content-Type": "application/json",
            "x-app-id": self.app_id,
            "x-app-sign": app_sign,
            "x-request-time": timestamp,
        }

    async def _post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """发送 POST 请求并处理标准异常."""
        if not self.is_configured:
            logger.warning("[KYB] 未配置跨运宝参数，跳过接口调用: %s", endpoint)
            return {}

        url = f"{self.base_url}{endpoint}"
        headers = self._build_headers(data)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers, timeout=15) as resp:
                    resp.raise_for_status()
                    result = await resp.json()

                    # 跨运宝的业务 code=0 代表成功 (可能是整型或字符串)
                    code = result.get("code")
                    if str(code) != "0":
                        logger.error("[KYB] 业务返回异常: %s -> %s", endpoint, result)
                    
                    return result

        except Exception as e:
            logger.error("[KYB] 网络或解析请求失败: %s -> %s", endpoint, e)
            return {}

    async def query_stock(self) -> dict[str, Any]:
        """查询库存 (示例预留接口).
        
        之后根据跨运宝真实的「库存查询」接口路径替换 endpoint 即可。
        """
        endpoint = "/open-sdk/wms/quick_query_stock"  # 替换为实际端点
        payload: dict[str, Any] = {
            # 填入实际查询参数
        }
        return await self._post(endpoint, payload)

    async def wms_stock_adjust(
        self,
        adjust_order_no: str,
        sku_id: int,
        adjust_qty: int,
        warehouse_code: str = "",
        remark: str = "TG Bot 库存同步",
    ) -> dict[str, Any]:
        """调用库存调整通知 (WMS -> KYB).
        
        Args:
            adjust_order_no: 库存调整单号 (必须唯一)
            sku_id: 商品 ID
            adjust_qty: 调整的数量 (正数增加，负数扣除)
            warehouse_code: 仓库编码 (如需要的话)
            remark: 备注
        """
        endpoint = "/open-sdk/oms/wms_stock_adjust"
        payload = {
            "adjustOrderNo": adjust_order_no,
            "warehouseCode": warehouse_code,
            "adjustDetails": [
                {
                    "skuId": sku_id,
                    # container 和 subContainer 通常跨运宝有要求填的话可以传入，空字符备用
                    "containerCode": "",
                    "subContainerCode": "",
                    "adjustQty": adjust_qty,
                    "remark": remark,
                }
            ]
        }
        return await self._post(endpoint, payload)


# 导出供全局调用的单例
kuayunbao_client = KuayunbaoClient()
