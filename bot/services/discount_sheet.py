"""促销折扣 Google Sheets 服务（Vandych VIP 专属）.

表格结构（列名由配置决定）：
  型号 | 折扣(%) | 链接 | 折扣码 | 是否有效 | 备注
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
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
CACHE_TTL = 300

COL_MODEL = "SKU"
COL_DISCOUNT = "discount"  # 折扣码
COL_LINK = "Links"
COL_CODE = "discount"      # 和折扣码同列
COL_ACTIVE = "active"      # 1/yes → 有效（可选列，缺省视为有效）
COL_NOTES = "Notes"

_redis_client: Redis | None = None


def _get_redis() -> Redis | None:
    global _redis_client
    if _redis_client is None and settings.redis_host:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


@dataclass
class DiscountItem:
    model: str
    discount: str   # 原始字符串如 "10%"
    link: str
    code: str
    active: bool = True
    notes: str = ""

    def format_copyable(self, lang: str = "zh") -> str:
        """生成用户可复制的折扣信息块."""
        labels = {
            "zh": ("SKU", "链接", "折扣码", "说明"),
            "en": ("SKU", "Links", "Code", "Notes"),
            "ru": ("SKU", "Ссылки", "Код", "Примечания"),
        }.get(lang, ("SKU", "Links", "Code", "Notes"))

        lines = [f"<b>{labels[0]}：</b><code>{self.model}</code>"]
        if self.link:
            lines.append(f"\n<b>{labels[1]}：</b>{self.link}")
        if self.code:
            lines.append(f"\n<b>{labels[2]}：</b><code>{self.code}</code>")
        if self.notes:
            lines.append(f"\n<b>{labels[3]}：</b>{self.notes}")
        elif self.discount:
            lines.append(f"\n<b>{labels[3]}：</b>{self.discount}")
        return "\n".join(lines)

    def format_text(self, lang: str = "zh") -> str:
        return self.format_copyable(lang)


def _row_value(row: dict[str, Any], *keys: str) -> str:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value).strip()
        value = normalized.get(key.strip().casefold())
        if value is not None:
            return str(value).strip()
    return ""


def _parse_rows(rows: list[dict[str, Any]]) -> list[DiscountItem]:
    items: list[DiscountItem] = []
    for row in rows:
        model = _row_value(row, COL_MODEL, "sku", "model", "型号", "产品编码")
        if not model:
            continue
        raw_active = _row_value(row, COL_ACTIVE, "active", "是否有效", "有效") or "1"
        active = raw_active.casefold() in ("1", "yes", "true", "是", "有效", "y")
        if not active:
            continue
        items.append(DiscountItem(
            model=model,
            discount=_row_value(row, COL_DISCOUNT, "discount", "折扣", "折扣码"),
            link=_row_value(row, COL_LINK, "links", "link", "链接"),
            code=_row_value(row, COL_CODE, "code", "discount", "折扣码"),
            active=active,
            notes=_row_value(row, COL_NOTES, "notes", "备注", "说明"),
        ))
    return items


def _parse_csv(csv_text: str) -> list[DiscountItem]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return _parse_rows(list(reader))


def _get_gspread_client() -> Any:
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(settings.google_credentials_file, scopes=scopes)
    return gspread.authorize(creds)


def _fetch_discount_rows_sync() -> list[dict[str, Any]]:
    gc = _get_gspread_client()
    spreadsheet = gc.open_by_key(settings.discount_sheet_id)
    gid = settings.discount_sheet_gid
    worksheet = next((ws for ws in spreadsheet.worksheets() if ws.id == gid), None)
    if worksheet is None:
        logger.warning("Discount worksheet gid=%s not found; using first worksheet", gid)
        worksheet = spreadsheet.sheet1
    return worksheet.get_all_records()


async def get_discounts() -> list[DiscountItem]:
    """获取当前有效的促销折扣列表."""
    sheet_id = settings.discount_sheet_id
    if not sheet_id:
        logger.warning("discount_sheet_id not configured")
        return []

    gid = settings.discount_sheet_gid
    cache_key = f"discount_items:{sheet_id}:{gid}"
    redis = _get_redis()

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return _parse_csv(cached)
        except Exception as exc:
            logger.warning("Redis read failed: %s", exc)

    creds_file = settings.google_credentials_file
    if creds_file and os.path.isfile(creds_file):
        try:
            rows = await asyncio.to_thread(_fetch_discount_rows_sync)
            items = _parse_rows(rows)
            return items
        except Exception as exc:
            logger.warning("Failed to fetch discount sheet via service account: %s", exc)

    url = SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    try:
        async with aiohttp.ClientSession(trust_env=True) as http:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                csv_text = await resp.text(encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to fetch discount sheet: %s", exc)
        return []

    if redis is not None:
        try:
            await redis.set(cache_key, csv_text, ex=CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis write failed: %s", exc)

    return _parse_csv(csv_text)


def _normalize(text: str) -> str:
    """标准化字符串用于模糊匹配：小写 + 去除空格/连字符/下划线."""
    import re
    return re.sub(r"[\s\-_]", "", text.lower())


def fuzzy_find(items: list[DiscountItem], query: str) -> list[tuple[int, DiscountItem]]:
    """模糊搜索 SKU，返回 (原始索引, item) 列表.

    匹配规则：标准化后的查询词是标准化 model 的子串，或反之。
    例如: "cpro"/"CPRO"/"jerry cpro" 都能命中 "Jerry-CPRO"
    """
    q = _normalize(query)
    if not q:
        return []
    results = []
    for idx, item in enumerate(items):
        m = _normalize(item.model)
        if q in m or m in q:
            results.append((idx, item))
    return results
