"""跨运宝 (KYB / Kuayunbao) WMS 接口客户端.

认证方式：HTTP 头中的 MD5 签名 (必需) + 可选静态 Token:
  x-app-id:       appId
  x-app-sign:     MD5(appSecret + timestamp + postJson)
  x-request-time: 毫秒级时间戳 (与签名一致)
  x-request-token: 静态 token (可选, 由 KYB_TOKEN 配置)

关键约束：签名的 postJson 必须与实际 POST body 完全相同 (紧凑无空格格式)。
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
        self.base_url = settings.kyb_api_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def _build_headers(self, body_json: str) -> dict[str, str]:
        """构建认证头. body_json 必须与实际 POST body 完全一致."""
        if not self.is_configured:
            raise ValueError("[KYB] 未配置 KYB_APP_ID / KYB_APP_SECRET")

        timestamp = str(int(time.time() * 1000))
        sign_src = self.app_secret + timestamp + body_json
        app_sign = hashlib.md5(sign_src.encode("utf-8")).hexdigest()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "x-app-id": str(self.app_id).strip(),
            "x-app-sign": app_sign,
            "x-request-time": timestamp,
        }

        if settings.kyb_token:
            headers["x-request-token"] = settings.kyb_token

        return headers

    async def _post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """发送 POST 请求. 签名与请求体使用同一 JSON 字符串."""
        if not self.is_configured:
            logger.warning("[KYB] 未配置跨运宝参数，跳过接口调用: %s", endpoint)
            return {}

        # 紧凑序列化 — 签名和请求体保持一致
        body_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        url = f"{self.base_url}{endpoint}"
        headers = self._build_headers(body_json)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=body_json.encode("utf-8"),
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    resp.raise_for_status()
                    result = await resp.json(content_type=None)

                    code = result.get("code")
                    if str(code) != "0":
                        logger.error("[KYB] 业务异常 %s -> code=%s msg=%s", endpoint, code, result.get("message"))

                    return result

        except aiohttp.ClientResponseError as e:
            logger.error("[KYB] HTTP %s: %s -> %s", e.status, endpoint, e.message)
        except Exception as e:
            logger.error("[KYB] 请求失败: %s -> %s", endpoint, e)
        return {}

    async def stock_total_query(
        self,
        platform_customer_code: str,
        warehouse_code_list: list[str] | None = None,
        sku_code_list: list[str] | None = None,
        sku_barcode_list: list[str] | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """总库存查询 (ERP -> KYB).

        Args:
            platform_customer_code: 平台客户编码 (必填)
            warehouse_code_list:    仓库编码列表 (可选)
            sku_code_list:          商品自定义编码列表 (可选)
            sku_barcode_list:       SKU 条码列表 (可选)
            page_index:             页码，默认 1
            page_size:              每页条数，最大 50

        Returns:
            {
              "code": 0,
              "data": [
                {
                  "skuCode": ...,        # 商品自定义编码
                  "skuName": ...,        # 商品中文名称
                  "tobUsableQty": ...,   # tob 可用库存
                  "tocUsableQty": ...,   # toc 可用库存
                  "tobTotalQty": ...,    # tob 库存总数
                  "tocTotalQty": ...,    # toc 库存总数
                  ...                   # 其他字段见 API 文档
                }
              ]
            }
        """
        endpoint = "/open-sdk/oms/stock_total_query"
        payload: dict[str, Any] = {
            "platformCustomerCode": platform_customer_code,
            "pageIndex": page_index,
            "pageSize": min(page_size, 50),
        }
        if warehouse_code_list:
            payload["warehouseCodeList"] = warehouse_code_list
        if sku_code_list:
            payload["skuCodeList"] = sku_code_list
        if sku_barcode_list:
            payload["skuBarcodeList"] = sku_barcode_list

        return await self._post(endpoint, payload)

    async def wms_stock_adjust(
        self,
        adjust_order_no: str,
        sku_id: int,
        adjust_qty: int,
        container_code: str = "",
        sub_container_code: str = "",
        warehouse_id: int | None = None,
        warehouse_code: str = "",
        warehouse_name: str = "",
        remark: str = "TG Bot 库存同步",
    ) -> dict[str, Any]:
        """库存调整通知 (WMS -> KYB).

        Args:
            adjust_order_no:    调整单号 (唯一, 必填)
            sku_id:             商品 ID (必填)
            adjust_qty:         调整数量，正数增加/负数扣减 (必填)
            container_code:     容器编码 (必填, 无则传空字符串)
            sub_container_code: 子容器编码 (必填, 无则传空字符串)
            warehouse_id:       仓库 ID (可选)
            warehouse_code:     仓库编码 (可选)
            warehouse_name:     仓库名称 (可选)
            remark:             备注
        """
        endpoint = "/open-sdk/oms/wms_stock_adjust"
        payload: dict[str, Any] = {
            "adjustOrderNo": adjust_order_no,
            "warehouseCode": warehouse_code,
            "warehouseName": warehouse_name,
            "adjustDetails": [
                {
                    "skuId": sku_id,
                    "containerCode": container_code,
                    "subContainerCode": sub_container_code,
                    "adjustQty": adjust_qty,
                    "remark": remark,
                }
            ],
        }
        if warehouse_id is not None:
            payload["warehouseId"] = warehouse_id
        return await self._post(endpoint, payload)


    async def get_stock_map(self, sku_barcodes: list[str]) -> dict[str, int]:
        """批量查询多个 SKU 的 toc 可用库存，返回 {skuBarcode: tocUsableQty}.

        - 跨仓库汇总（多仓库同一 SKU 的 tocUsableQty 相加）
        - 每批次最多 50 个 SKU（KYB 限制）
        - 若未配置 kyb_platform_customer_code 则返回空字典
        """
        if not sku_barcodes or not settings.kyb_platform_customer_code:
            return {}

        customer_code = settings.kyb_platform_customer_code
        stock_map: dict[str, int] = {}

        for i in range(0, len(sku_barcodes), 50):
            batch = sku_barcodes[i : i + 50]
            page = 1
            while True:
                result = await self.stock_total_query(
                    platform_customer_code=customer_code,
                    sku_barcode_list=batch,
                    page_index=page,
                    page_size=50,
                )
                data = result.get("data") or []
                if not data:
                    break
                for item in data:
                    barcode = item.get("skuBarcode", "")
                    if barcode:
                        stock_map[barcode] = (
                            stock_map.get(barcode, 0) + item.get("tocUsableQty", 0)
                        )
                if len(data) < 50:
                    break
                page += 1

        return stock_map


kuayunbao_client = KuayunbaoClient()
