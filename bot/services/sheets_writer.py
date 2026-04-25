"""Google Sheets 写入服务.

使用 gspread + Service Account 将计算好的 QTYS 写回 Google Sheets。
表格列结构（固定）：SKU | QTYS | state | Notes
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from bot.config import settings
from bot.services.outdoor_sheets import OUTDOOR_SHEET_CONFIG
from bot.services.sheets import SHEET_CONFIG, SHEET_ID

logger = logging.getLogger(__name__)

# QTYS 列的字母（B 列，即第 2 列）
QTYS_COL = 2
STATE_COL = 3
NOTES_COL = 4
HEADER_ROW = 1  # 第 1 行是表头，数据从第 2 行开始


@dataclass(frozen=True)
class SheetRowUpdate:
    """单行库存回写数据."""

    qty: int
    state: str | None = None
    notes: str | None = None


def _get_gspread_client() -> Any:
    """构建 gspread 客户端（同步，运行在线程池）."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError("请先安装依赖：pip install gspread google-auth")

    creds_file = settings.google_credentials_file
    if not os.path.exists(creds_file):
        raise FileNotFoundError(
            f"Google Service Account JSON 不存在: {creds_file}\n"
            "请按文档配置 Google Sheets 写权限后重试。"
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    return gspread.authorize(creds)


def _resolve_sheet_target(sheet_key: str) -> tuple[str, int] | None:
    """解析写入目标，优先使用新版 Outdoor 库存表."""
    outdoor_config = OUTDOOR_SHEET_CONFIG.get(sheet_key)
    if outdoor_config:
        if not settings.outdoor_sheet_id:
            raise ValueError("OUTDOOR_SHEET_ID 未配置，无法写入 Outdoor 库存表")
        return settings.outdoor_sheet_id, int(outdoor_config["gid"])

    legacy_config = SHEET_CONFIG.get(sheet_key)
    if legacy_config:
        return SHEET_ID, int(legacy_config["gid"])

    return None


def _write_qtys_sync(sheet_key: str, updates: dict[str, int]) -> int:
    """同步写入 QTYS 到 Google Sheets，返回更新行数.

    updates: {sku: new_qty}
    只更新已存在的 SKU 行，不增减行。
    """
    if not updates:
        return 0

    target = _resolve_sheet_target(sheet_key)
    if not target:
        logger.error("[SheetsWriter] 未知 sheet_key: %s", sheet_key)
        return 0

    import gspread

    sheet_id, gid = target
    gc = _get_gspread_client()
    sh = gc.open_by_key(sheet_id)

    # 通过 GID 找到对应 worksheet
    worksheet: Any = None
    for ws in sh.worksheets():
        if ws.id == gid:
            worksheet = ws
            break
    if worksheet is None:
        logger.error("[SheetsWriter] 找不到 GID=%d 的 worksheet", gid)
        return 0

    # 读取所有数据（含表头）
    all_values: list[list[str]] = worksheet.get_all_values()
    if len(all_values) <= HEADER_ROW:
        logger.warning("[SheetsWriter] Sheet %s 无数据行", sheet_key)
        return 0

    # 找到 SKU 列索引（第 1 列，索引 0）
    updated = 0
    batch_updates: list[gspread.Cell] = []

    for row_idx, row in enumerate(all_values[HEADER_ROW:], start=HEADER_ROW + 1):
        if not row:
            continue
        sku = row[0].strip() if row else ""
        if sku in updates:
            cell = gspread.Cell(row=row_idx, col=QTYS_COL, value=updates[sku])
            batch_updates.append(cell)
            updated += 1

    if batch_updates:
        worksheet.update_cells(batch_updates, value_input_option="USER_ENTERED")
        logger.info("[SheetsWriter] %s: 更新 %d 行 QTYS", sheet_key, updated)

    return updated


def _write_inventory_rows_sync(sheet_key: str, updates: dict[str, SheetRowUpdate]) -> int:
    """同步写入 QTYS / State / Notes 到 Google Sheets，返回更新行数."""
    if not updates:
        return 0

    target = _resolve_sheet_target(sheet_key)
    if not target:
        logger.error("[SheetsWriter] 未知 sheet_key: %s", sheet_key)
        return 0

    import gspread

    sheet_id, gid = target
    gc = _get_gspread_client()
    sh = gc.open_by_key(sheet_id)

    worksheet: Any = None
    for ws in sh.worksheets():
        if ws.id == gid:
            worksheet = ws
            break
    if worksheet is None:
        logger.error("[SheetsWriter] 找不到 GID=%d 的 worksheet", gid)
        return 0

    all_values: list[list[str]] = worksheet.get_all_values()
    if len(all_values) <= HEADER_ROW:
        logger.warning("[SheetsWriter] Sheet %s 无数据行", sheet_key)
        return 0

    updated = 0
    batch_updates: list[gspread.Cell] = []

    for row_idx, row in enumerate(all_values[HEADER_ROW:], start=HEADER_ROW + 1):
        if not row:
            continue
        sku = row[0].strip() if row else ""
        update = updates.get(sku)
        if update is None:
            continue

        batch_updates.append(gspread.Cell(row=row_idx, col=QTYS_COL, value=update.qty))
        if update.state is not None:
            batch_updates.append(gspread.Cell(row=row_idx, col=STATE_COL, value=update.state))
        if update.notes is not None:
            batch_updates.append(gspread.Cell(row=row_idx, col=NOTES_COL, value=update.notes))
        updated += 1

    if batch_updates:
        worksheet.update_cells(batch_updates, value_input_option="USER_ENTERED")
        logger.info("[SheetsWriter] %s: 更新 %d 行库存字段", sheet_key, updated)

    return updated


async def write_qtys_to_sheet(sheet_key: str, updates: dict[str, int]) -> int:
    """异步写入 QTYS，在线程池中执行 gspread 同步操作."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _write_qtys_sync, sheet_key, updates)


async def write_inventory_rows_to_sheet(sheet_key: str, updates: dict[str, SheetRowUpdate]) -> int:
    """异步写入 QTYS / State / Notes，在线程池中执行 gspread 同步操作."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _write_inventory_rows_sync, sheet_key, updates)
