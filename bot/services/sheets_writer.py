"""Google Sheets 写入服务.

使用 gspread + Service Account 将计算好的库存写回 Google Sheets。
Bot 展示表结构：SKU | QTYS | state | Notes
内部同步表结构：SKU | QTYS | 在途库存（只回填 QTYS）
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from bot.config import settings
from bot.services.sheets import SHEET_CONFIG, SHEET_ID

logger = logging.getLogger(__name__)

# QTYS 列的字母（B 列，即第 2 列）
QTYS_COL = 2
STATE_COL = 3
NOTES_COL = 4
HEADER_ROW = 1  # 第 1 行是表头，数据从第 2 行开始


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


def _write_qtys_sync(
    sheet_key: str,
    updates: dict[str, int],
    state_updates: dict[str, str] | None = None,
    note_updates: dict[str, str] | None = None,
) -> int:
    """同步写入 QTYS 到 Google Sheets，返回更新行数.

    updates: {sku: new_qty}
    state_updates: {sku: state}，公开 Bot 表写入 C 列。
    note_updates: {sku: note}，公开 Bot 表写入 D 列。
    只更新已存在的 SKU 行，不增减行。
    """
    if not updates:
        return 0

    config = SHEET_CONFIG.get(sheet_key)
    if not config:
        logger.error("[SheetsWriter] 未知 sheet_key: %s", sheet_key)
        return 0

    import gspread

    gid = int(config["gid"])
    gc = _get_gspread_client()
    sh = gc.open_by_key(SHEET_ID)

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
            batch_updates.append(gspread.Cell(row=row_idx, col=QTYS_COL, value=updates[sku]))
            if state_updates is not None:
                batch_updates.append(gspread.Cell(row=row_idx, col=STATE_COL, value=state_updates.get(sku, "")))
            if note_updates is not None:
                batch_updates.append(gspread.Cell(row=row_idx, col=NOTES_COL, value=note_updates.get(sku, "")))
            updated += 1

    if batch_updates:
        worksheet.update_cells(batch_updates, value_input_option="USER_ENTERED")
        columns = "QTYS"
        if state_updates is not None or note_updates is not None:
            columns = "QTYS/State/Notes"
        logger.info("[SheetsWriter] %s: 更新 %d 行 %s", sheet_key, updated, columns)

    return updated


async def write_qtys_to_sheet(
    sheet_key: str,
    updates: dict[str, int],
    state_updates: dict[str, str] | None = None,
    note_updates: dict[str, str] | None = None,
) -> int:
    """异步写入 QTYS，在线程池中执行 gspread 同步操作."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _write_qtys_sync, sheet_key, updates, state_updates, note_updates)
