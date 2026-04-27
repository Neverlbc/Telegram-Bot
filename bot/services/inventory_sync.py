"""库存同步编排服务.

核心公式：QTYS = 跨运宝 tocUsableQty - 聚水潭 order_lock

执行步骤（每个 sheet_key 独立执行）：
  1. 从 Google Sheets 读取当前所有 SKU
  2. 并发查询聚水潭 + 跨运宝
  3. 计算 QTYS = kyb_toc_usable_qty - jst_order_lock（最小为 0）
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

from bot.config import settings
from bot.services.jushuitan import jushuitan_client
from bot.services.kuayunbao import kuayunbao_client
from bot.services.outdoor_sheets import OUTDOOR_SHEET_CONFIG, clear_outdoor_cache, get_outdoor_sync_rows
from bot.services.outdoor_sku_aliases import DEFAULT_SKU_ALIASES
from bot.services.sheets_writer import SheetRowUpdate, write_inventory_rows_to_sheet

logger = logging.getLogger(__name__)

AUTO_MANAGED_NOTE_TEXTS = {
    "",
    "none",
    "null",
    "n/a",
    "在途中",
    "正在运输途中",
    "in transit",
    "в пути",
    "для получения более подробной информации, пожалуйста, свяжитесь со службой поддержки клиентов",
}


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
    """清除 Redis 中的 Outdoor 库存缓存."""
    try:
        await clear_outdoor_cache()
    except Exception as e:
        logger.warning("[Sync] 清缓存失败 %s: %s", sheet_key, e)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _jst_plus_variants(sku: str) -> list[str]:
    stripped = " ".join(sku.strip().split())
    if "+" not in stripped:
        return []

    compact_plus = stripped.replace(" + ", "+")
    variants = [compact_plus.replace("+", "十")]
    return _unique(variants)


def _get_sku_alias_map() -> dict[str, dict[str, list[str]]]:
    aliases: dict[str, dict[str, list[str]]] = {
        sku: {
            "jst": list(config.get("jst", [])),
            "kyb": list(config.get("kyb", [])),
        }
        for sku, config in DEFAULT_SKU_ALIASES.items()
    }
    try:
        env_aliases = settings.outdoor_sku_alias_map
    except Exception as e:
        logger.error("[Sync] OUTDOOR_SKU_ALIASES 解析失败: %s", e)
        env_aliases = {}

    for sku, config in env_aliases.items():
        current = aliases.setdefault(sku, {"jst": [], "kyb": []})
        current["jst"] = _unique([*current.get("jst", []), *config.get("jst", [])])
        current["kyb"] = _unique([*current.get("kyb", []), *config.get("kyb", [])])
    return aliases


def _source_skus(sheet_sku: str, source: str, aliases: dict[str, dict[str, list[str]]]) -> list[str]:
    source_aliases = aliases.get(sheet_sku, {}).get(source, [])
    if source_aliases:
        if source == "jst":
            variants = [variant for sku in source_aliases for variant in _jst_plus_variants(sku)]
            return _unique([*source_aliases, *variants])
        return _unique(source_aliases)
    if source == "jst":
        return _unique([sheet_sku, *_jst_plus_variants(sheet_sku)])
    return [sheet_sku]


def _sum_source_qty(
    stock_map: dict[str, int],
    sheet_sku: str,
    source: str,
    aliases: dict[str, dict[str, list[str]]],
) -> int:
    return sum(int(stock_map.get(sku, 0) or 0) for sku in _source_skus(sheet_sku, source, aliases))


def _found_in_source(
    stock_map: dict[str, int],
    sheet_sku: str,
    source: str,
    aliases: dict[str, dict[str, list[str]]],
) -> bool:
    return any(sku in stock_map for sku in _source_skus(sheet_sku, source, aliases))


def _is_auto_managed_note(note: str) -> bool:
    normalized = " ".join((note or "").strip().split()).casefold().rstrip(".。")
    return normalized in AUTO_MANAGED_NOTE_TEXTS


def _next_note(qty: int, current_note: str) -> str:
    if not _is_auto_managed_note(current_note):
        return current_note
    if qty > 0:
        return ""
    return "在途中"


async def sync_sheet(sheet_key: str) -> SyncResult:
    """同步单个分类 sheet 的库存数据."""
    logger.info("[Sync] 开始同步: %s", sheet_key)

    # ── 1. 读取当前 Outdoor Sheets SKU 列表 ─────────────
    rows = await get_outdoor_sync_rows(sheet_key)
    if not rows:
        return SyncResult(sheet_key=sheet_key, total_skus=0, updated_rows=0,
                          jst_found=0, kyb_found=0, error="Outdoor Sheets 无 SKU 行")

    aliases = _get_sku_alias_map()
    product_rows = [row for row in rows if not row.is_brand_header]
    sheet_skus = list(dict.fromkeys(row.sku for row in product_rows))
    jst_sku_list = _unique([sku for sheet_sku in sheet_skus for sku in _source_skus(sheet_sku, "jst", aliases)])
    kyb_sku_list = _unique([sku for sheet_sku in sheet_skus for sku in _source_skus(sheet_sku, "kyb", aliases)])
    logger.info("[Sync] %s: %d 个表格 SKU，JST 查询 %d 个，KYB 查询 %d 个",
                sheet_key, len(sheet_skus), len(jst_sku_list), len(kyb_sku_list))

    # ── 2. 并发查询聚水潭 + 跨运宝 ────────────────────────
    jst_task = asyncio.create_task(jushuitan_client.get_stock_map(jst_sku_list))
    kyb_task = asyncio.create_task(kuayunbao_client.get_stock_map(kyb_sku_list))
    jst_map, kyb_map = await asyncio.gather(jst_task, kyb_task, return_exceptions=True)

    if isinstance(jst_map, Exception):
        logger.error("[Sync] 聚水潭查询失败: %s", jst_map)
        jst_map = {}
    if isinstance(kyb_map, Exception):
        logger.error("[Sync] 跨运宝查询失败: %s", kyb_map)
        kyb_map = {}

    jst_found = sum(1 for sku in sheet_skus if _found_in_source(jst_map, sku, "jst", aliases))
    kyb_found = sum(1 for sku in sheet_skus if _found_in_source(kyb_map, sku, "kyb", aliases))
    logger.info("[Sync] %s: 聚水潭 %d/%d，跨运宝 %d/%d",
                sheet_key, jst_found, len(sheet_skus), kyb_found, len(sheet_skus))

    # ── 3. 计算 QTYS ─────────────────────────────────────
    # 公式：QTYS = KYB tocUsableQty - 聚水潭 order_lock（订单占有数）
    updates: dict[str, SheetRowUpdate] = {}
    for row in product_rows:
        kyb_usable = _sum_source_qty(kyb_map, row.sku, "kyb", aliases)
        jst_order_lock = _sum_source_qty(jst_map, row.sku, "jst", aliases)
        net = max(0, kyb_usable - jst_order_lock)
        updates[row.sku] = SheetRowUpdate(
            qty=net,
            state="有货" if net > 0 else "缺货",
            notes=_next_note(net, row.notes),
        )

    # ── 4. 写回 Sheets ────────────────────────────────────
    try:
        updated_rows = await write_inventory_rows_to_sheet(sheet_key, updates)
    except Exception as e:
        logger.error("[Sync] 写 Sheets 失败 %s: %s", sheet_key, e)
        return SyncResult(sheet_key=sheet_key, total_skus=len(sheet_skus),
                          updated_rows=0, jst_found=jst_found, kyb_found=kyb_found,
                          error=str(e))

    # ── 5. 清缓存 ─────────────────────────────────────────
    await _clear_sheet_cache(sheet_key)

    logger.info("[Sync] %s 完成: 写入 %d 行", sheet_key, updated_rows)
    return SyncResult(sheet_key=sheet_key, total_skus=len(sheet_skus),
                      updated_rows=updated_rows, jst_found=jst_found, kyb_found=kyb_found)


async def sync_all_sheets() -> list[SyncResult]:
    """同步所有已配置的 Outdoor sheet."""
    results = []
    for sheet_key in OUTDOOR_SHEET_CONFIG:
        result = await sync_sheet(sheet_key)
        results.append(result)
    return results
