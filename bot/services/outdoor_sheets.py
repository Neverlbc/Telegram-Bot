"""莫斯科户外现货 Google Sheets 服务.

两个 tab：
  完整版 (GID=0)          — VIP 视图，所有品牌
  阈割版 (GID=644083927)  — 公开视图，部分品牌

表格列：SKU | QTYS | State | Notes
品牌标题行（QTYS 为空）自动跳过。
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import aiohttp
from redis.asyncio import Redis

from bot.config import settings

logger = logging.getLogger(__name__)

SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d"
    "/{sheet_id}/export?format=csv&gid={gid}"
)
CACHE_TTL = 300  # 5 分钟

# 列名常量 — 与 Google Sheet 实际表头对应
COL_SKU   = "SKU"
COL_QTY   = "QTYS"
COL_STATE = "State"
COL_NOTES = "Notes"

# Tab GID 配置
OUTDOOR_GID_FULL     = 0          # Stock_Outdoor【完整版】VIP 视图
OUTDOOR_GID_FILTERED = 644083927  # Stock_Outdoor【阈割版】公开视图

OUTDOOR_SHEET_CONFIG: dict[str, dict[str, str | int | bool]] = {
    "outdoor_vip": {
        "gid": OUTDOOR_GID_FULL,
        "vip": True,
        "name": "VIP 完整库存",
    },
    "outdoor_public": {
        "gid": OUTDOOR_GID_FILTERED,
        "vip": False,
        "name": "公开库存",
    },
}

_DIGIT_RE = re.compile(r"\d")

_redis_client: Redis | None = None


def _get_redis() -> Redis | None:
    global _redis_client
    if _redis_client is None and settings.redis_host:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


@dataclass
class OutdoorItem:
    sku: str
    qty: int
    state: str = ""   # Sheet 中 State 列原始值
    notes: str = ""
    brand: str = ""

    @property
    def is_available(self) -> bool:
        return self.qty > 0

    def status_text(self, lang: str = "zh") -> str:
        if self.state:
            return self.state
        if self.is_available:
            return {"zh": "✅ 有货", "en": "✅ In stock", "ru": "✅ В наличии"}.get(lang, "✅ 有货")
        return {"zh": "❌ 无货", "en": "❌ Out of stock", "ru": "❌ Нет в наличии"}.get(lang, "❌ 无货")


@dataclass
class OutdoorSyncRow:
    """库存同步用行数据，保留空 QTYS 行以便计算后回写."""

    sku: str
    qty_text: str = ""
    state: str = ""
    notes: str = ""
    brand_header: bool = False
    merge_metadata_known: bool = False

    @property
    def has_existing_qty(self) -> bool:
        return bool(self.qty_text.strip())

    @property
    def is_brand_header(self) -> bool:
        if self.merge_metadata_known:
            return self.brand_header
        return _is_brand_header(self.sku, self.qty_text, self.state, self.notes)


def _is_brand_header(sku: str, qty_text: str = "", state: str = "", notes: str = "") -> bool:
    """识别 CSV 中的品牌表头行.

    Google CSV 不包含行背景/字体样式，无法直接读取黑底或黄底品牌行。
    当前表格约定品牌行只有 SKU 列有值，且品牌名通常不含数字；
    产品编码通常包含数字或已有 QTYS/State/Notes。
    """
    sku = sku.strip()
    return bool(sku and not qty_text.strip() and not state.strip() and not notes.strip() and not _DIGIT_RE.search(sku))


async def _fetch_outdoor_csv(gid: int) -> str:
    url = SHEETS_CSV_URL.format(sheet_id=settings.outdoor_sheet_id, gid=gid)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as http:
        async with http.get(url) as resp:
            resp.raise_for_status()
            return await resp.text(encoding="utf-8")


def _parse_csv(csv_text: str) -> list[OutdoorItem]:
    items: list[OutdoorItem] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    current_brand = ""
    for row in reader:
        sku = row.get(COL_SKU, "").strip()
        if not sku:
            continue
        qty_str = row.get(COL_QTY, "").strip()
        state = row.get(COL_STATE, "").strip()
        notes = row.get(COL_NOTES, "").strip()
        if _is_brand_header(sku, qty_str, state, notes):
            current_brand = sku
            continue
        try:
            qty = int(qty_str or "0")
        except ValueError:
            qty = 0
        items.append(OutdoorItem(sku=sku, qty=qty, state=state, notes=notes, brand=current_brand))
    return items


def _parse_sync_rows(csv_text: str) -> list[OutdoorSyncRow]:
    rows: list[OutdoorSyncRow] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        sku = row.get(COL_SKU, "").strip()
        if not sku:
            continue
        rows.append(
            OutdoorSyncRow(
                sku=sku,
                qty_text=row.get(COL_QTY, "").strip(),
                state=row.get(COL_STATE, "").strip(),
                notes=row.get(COL_NOTES, "").strip(),
            )
        )
    return rows


def _get_gspread_client() -> Any:
    import gspread
    from google.oauth2.service_account import Credentials

    creds_file = settings.google_credentials_file
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    return gspread.authorize(creds)


def _fetch_sync_rows_with_merges_sync(gid: int) -> list[OutdoorSyncRow]:
    """通过 Sheets API 读取行和合并单元格信息，用 A:D 合并识别品牌表头."""
    if not settings.outdoor_sheet_id:
        return []

    gc = _get_gspread_client()
    spreadsheet = gc.open_by_key(settings.outdoor_sheet_id)

    worksheet: Any = None
    for ws in spreadsheet.worksheets():
        if ws.id == gid:
            worksheet = ws
            break
    if worksheet is None:
        return []

    metadata = spreadsheet.fetch_sheet_metadata(params={"includeGridData": "false"})
    sheet_meta = next(
        (
            sheet
            for sheet in metadata.get("sheets", [])
            if int(sheet.get("properties", {}).get("sheetId", -1)) == gid
        ),
        {},
    )
    header_rows: set[int] = set()
    for merge in sheet_meta.get("merges", []):
        start_row = int(merge.get("startRowIndex", 0))
        end_row = int(merge.get("endRowIndex", 0))
        start_col = int(merge.get("startColumnIndex", 0))
        end_col = int(merge.get("endColumnIndex", 0))
        if start_col == 0 and end_col >= 4 and end_row == start_row + 1:
            header_rows.add(start_row + 1)

    values: list[list[str]] = worksheet.get_all_values()
    rows: list[OutdoorSyncRow] = []
    for row_number, values_row in enumerate(values[1:], start=2):
        padded = [*values_row, "", "", "", ""]
        sku = padded[0].strip()
        if not sku:
            continue
        rows.append(
            OutdoorSyncRow(
                sku=sku,
                qty_text=padded[1].strip(),
                state=padded[2].strip(),
                notes=padded[3].strip(),
                brand_header=row_number in header_rows,
                merge_metadata_known=True,
            )
        )
    return rows


async def get_outdoor_inventory(vip: bool = False) -> list[OutdoorItem]:
    """获取户外类库存列表.

    vip=True  → 读完整版 tab（全品牌）
    vip=False → 读阈割版 tab（公开品牌）
    """
    sheet_id = settings.outdoor_sheet_id
    if not sheet_id:
        logger.warning("outdoor_sheet_id not configured")
        return []

    gid = OUTDOOR_GID_FULL if vip else OUTDOOR_GID_FILTERED
    cache_key = f"outdoor_inv:{'vip' if vip else 'pub'}"
    redis = _get_redis()

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return _parse_csv(cached)
        except Exception as e:
            logger.warning("Redis read failed: %s", e)

    try:
        csv_text = await _fetch_outdoor_csv(gid)
    except Exception as e:
        logger.error("Failed to fetch outdoor sheet: %r", e)
        return []

    if redis is not None:
        try:
            await redis.set(cache_key, csv_text, ex=CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed: %s", e)

    return _parse_csv(csv_text)


async def get_outdoor_sync_rows(sheet_key: str) -> list[OutdoorSyncRow]:
    """读取 Outdoor 同步目标表的 SKU 行.

    与展示查询不同，同步必须读取 QTYS 为空的 SKU 行，否则首次回写无法覆盖空表。
    """
    sheet_id = settings.outdoor_sheet_id
    if not sheet_id:
        logger.warning("outdoor_sheet_id not configured")
        return []

    config = OUTDOOR_SHEET_CONFIG.get(sheet_key)
    if not config:
        logger.warning("Unknown outdoor sheet_key: %s", sheet_key)
        return []

    gid = int(config["gid"])
    creds_file = settings.google_credentials_file
    if creds_file and os.path.isfile(creds_file):
        try:
            rows = await asyncio.to_thread(_fetch_sync_rows_with_merges_sync, gid)
            if rows:
                return rows
        except Exception as e:
            logger.warning("Failed to fetch outdoor sync rows with merge metadata %s (gid=%d): %r", sheet_key, gid, e)

    try:
        csv_text = await _fetch_outdoor_csv(gid)
    except Exception as e:
        logger.error("Failed to fetch outdoor sync sheet %s (gid=%d): %r", sheet_key, gid, e)
        return []

    return _parse_sync_rows(csv_text)


async def clear_outdoor_cache() -> None:
    redis = _get_redis()
    if redis is not None:
        for key in ("outdoor_inv:vip", "outdoor_inv:pub"):
            try:
                await redis.delete(key)
            except Exception:
                pass
