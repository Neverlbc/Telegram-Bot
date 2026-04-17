"""库存同步编排服务.

核心公式：QTYS = 聚水潭主仓实际库存(qty) - 跨运宝 tocUsableQty

执行步骤（每个 sheet_key 独立执行）：
  1. 从 Google Sheets 读取当前所有 SKU
  2. 并发查询聚水潭 + 跨运宝
  3. 计算 QTYS = jst_qty - kyb_qty（最小为 0）
  4. 将 QTYS 批量写回 Google Sheets
  5. 清除 Redis 库存缓存（让 Bot 下次读到最新数据）

调用入口：
  - Bot 管理命令 /sync_inventory
  - 未来可接定时任务
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bot.services.jushuitan import jushuitan_client
from bot.services.kuayunbao import kuayunbao_client
from bot.services.sheets import CACHE_TTL, SHEET_CONFIG, get_inventory, get_redis_client
from bot.services.sheets_writer import write_qtys_to_sheet

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """单次同步结果."""

    sheet_key: str
    total_skus: int
    updated_rows: int
    jst_found: int       # 聚水潭查到的 SKU 数
    kyb_found: int       # 跨运宝查到的 SKU 数
    error: str | None = None


async def _clear_sheet_cache(sheet_key: str) -> None:
    """清除 Redis 中该 sheet 的库存缓存."""
    redis = get_redis_client()
    if redis is None:
        return
    config = SHEET_CONFIG.get(sheet_key, {})
    gid = config.get("gid", 0)
    keys = [
        f"inventory:{sheet_key}:{gid}",
        f"kyb_stock:{sheet_key}",
    ]
    try:
        await redis.delete(*keys)
    except Exception as e:
        logger.warning("[Sync] 清缓存失败 %s: %s", sheet_key, e)


async def sync_sheet(sheet_key: str) -> SyncResult:
    """同步单个分类 sheet 的库存数据."""
    logger.info("[Sync] 开始同步: %s", sheet_key)

    # ── 1. 读取当前 Sheets SKU 列表 ──────────────────────
    items = await get_inventory(sheet_key)
    if not items:
        return SyncResult(sheet_key=sheet_key, total_skus=0, updated_rows=0,
                          jst_found=0, kyb_found=0, error="Sheets 无数据")

    sku_list = [item.sku for item in items]
    logger.info("[Sync] %s: %d 个 SKU", sheet_key, len(sku_list))

    # ── 2. 并发查询聚水潭 + 跨运宝 ────────────────────────
    jst_task = asyncio.create_task(jushuitan_client.get_stock_map(sku_list))
    kyb_task = asyncio.create_task(kuayunbao_client.get_stock_map(sku_list))
    jst_map, kyb_map = await asyncio.gather(jst_task, kyb_task, return_exceptions=False)

    if isinstance(jst_map, Exception):
        logger.error("[Sync] 聚水潭查询失败: %s", jst_map)
        jst_map = {}
    if isinstance(kyb_map, Exception):
        logger.error("[Sync] 跨运宝查询失败: %s", kyb_map)
        kyb_map = {}

    jst_found = sum(1 for sku in sku_list if sku in jst_map)
    kyb_found = sum(1 for sku in sku_list if sku in kyb_map)
    logger.info("[Sync] %s: 聚水潭 %d/%d，跨运宝 %d/%d",
                sheet_key, jst_found, len(sku_list), kyb_found, len(sku_list))

    # ── 3. 计算 QTYS ─────────────────────────────────────
    updates: dict[str, int] = {}
    for item in items:
        jst_qty = jst_map.get(item.sku, item.qty)   # 未查到则保留原值
        kyb_qty = kyb_map.get(item.sku, 0)
        net = max(0, jst_qty - kyb_qty)
        updates[item.sku] = net

    # ── 4. 写回 Sheets ────────────────────────────────────
    try:
        updated_rows = await write_qtys_to_sheet(sheet_key, updates)
    except Exception as e:
        logger.error("[Sync] 写 Sheets 失败 %s: %s", sheet_key, e)
        return SyncResult(sheet_key=sheet_key, total_skus=len(sku_list),
                          updated_rows=0, jst_found=jst_found, kyb_found=kyb_found,
                          error=str(e))

    # ── 5. 清缓存 ─────────────────────────────────────────
    await _clear_sheet_cache(sheet_key)

    logger.info("[Sync] %s 完成: 写入 %d 行", sheet_key, updated_rows)
    return SyncResult(sheet_key=sheet_key, total_skus=len(sku_list),
                      updated_rows=updated_rows, jst_found=jst_found, kyb_found=kyb_found)


async def sync_all_sheets() -> list[SyncResult]:
    """同步所有已配置的 sheet 分类."""
    results = []
    for sheet_key in SHEET_CONFIG:
        result = await sync_sheet(sheet_key)
        results.append(result)
    return results
