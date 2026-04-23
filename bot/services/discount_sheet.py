"""促销折扣 Google Sheets 服务（Vandych VIP 专属）.

表格结构（列名由配置决定）：
  型号 | 折扣(%) | 链接 | 折扣码 | 是否有效 | 备注
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass

import aiohttp
from redis.asyncio import Redis

from bot.config import settings

logger = logging.getLogger(__name__)

SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d"
    "/{sheet_id}/export?format=csv&gid={gid}"
)
CACHE_TTL = 300

COL_MODEL = "型号"
COL_DISCOUNT = "折扣"     # 如 "10%"
COL_LINK = "链接"
COL_CODE = "折扣码"
COL_ACTIVE = "是否有效"  # 1/yes → 有效
COL_NOTES = "备注"

DISCOUNT_GID = 0

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

    def format_text(self, lang: str = "zh") -> str:
        parts = []
        if lang == "zh":
            parts.append(f"🏷 <b>{self.model}</b>  折扣：{self.discount}")
        elif lang == "en":
            parts.append(f"🏷 <b>{self.model}</b>  Discount: {self.discount}")
        else:
            parts.append(f"🏷 <b>{self.model}</b>  Скидка: {self.discount}")
        if self.code:
            parts.append(f"🔑 {self.code}")
        if self.link:
            parts.append(f"🛒 {self.link}")
        if self.notes:
            parts.append(f"📝 {self.notes}")
        return "\n".join(parts)


def _parse_csv(csv_text: str) -> list[DiscountItem]:
    items: list[DiscountItem] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        model = row.get(COL_MODEL, "").strip()
        if not model:
            continue
        raw_active = str(row.get(COL_ACTIVE, "1")).strip().lower()
        active = raw_active in ("1", "yes", "true", "是", "有效", "y")
        if not active:
            continue
        items.append(DiscountItem(
            model=model,
            discount=row.get(COL_DISCOUNT, "").strip(),
            link=row.get(COL_LINK, "").strip(),
            code=row.get(COL_CODE, "").strip(),
            active=active,
            notes=row.get(COL_NOTES, "").strip(),
        ))
    return items


async def get_discounts() -> list[DiscountItem]:
    """获取当前有效的促销折扣列表."""
    sheet_id = settings.discount_sheet_id
    if not sheet_id:
        logger.warning("discount_sheet_id not configured")
        return []

    cache_key = "discount_items"
    redis = _get_redis()

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return _parse_csv(cached)
        except Exception as e:
            logger.warning("Redis read failed: %s", e)

    url = SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=DISCOUNT_GID)
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                csv_text = await resp.text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to fetch discount sheet: %s", e)
        return []

    if redis is not None:
        try:
            await redis.set(cache_key, csv_text, ex=CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed: %s", e)

    return _parse_csv(csv_text)
