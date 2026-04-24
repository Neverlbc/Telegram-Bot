"""莫斯科户外现货 Google Sheets 服务.

两个 tab：
  完整版 (GID=0)          — VIP 视图，所有品牌
  阈割版 (GID=644083927)  — 公开视图，部分品牌

表格列：SKU | QTYS | State | Notes
品牌标题行（QTYS 为空）自动跳过。
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
CACHE_TTL = 300  # 5 分钟

# 列名常量 — 与 Google Sheet 实际表头对应
COL_SKU   = "SKU"
COL_QTY   = "QTYS"
COL_STATE = "State"
COL_NOTES = "Notes"

# Tab GID 配置
OUTDOOR_GID_FULL     = 0          # Stock_Outdoor【完整版】VIP 视图
OUTDOOR_GID_FILTERED = 644083927  # Stock_Outdoor【阈割版】公开视图

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

    @property
    def is_available(self) -> bool:
        return self.qty > 0

    def status_text(self, lang: str = "zh") -> str:
        if self.state:
            return self.state
        if self.is_available:
            return {"zh": "✅ 有货", "en": "✅ In stock", "ru": "✅ В наличии"}.get(lang, "✅ 有货")
        return {"zh": "❌ 无货", "en": "❌ Out of stock", "ru": "❌ Нет в наличии"}.get(lang, "❌ 无货")


def _parse_csv(csv_text: str) -> list[OutdoorItem]:
    items: list[OutdoorItem] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        sku = row.get(COL_SKU, "").strip()
        if not sku:
            continue
        qty_str = row.get(COL_QTY, "").strip()
        if not qty_str:
            # QTYS 为空 → 品牌标题行，跳过
            continue
        try:
            qty = int(qty_str)
        except ValueError:
            qty = 0
        state = row.get(COL_STATE, "").strip()
        notes = row.get(COL_NOTES, "").strip()
        items.append(OutdoorItem(sku=sku, qty=qty, state=state, notes=notes))
    return items


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

    url = SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                csv_text = await resp.text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to fetch outdoor sheet: %s", e)
        return []

    if redis is not None:
        try:
            await redis.set(cache_key, csv_text, ex=CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed: %s", e)

    return _parse_csv(csv_text)


async def clear_outdoor_cache() -> None:
    redis = _get_redis()
    if redis is not None:
        for key in ("outdoor_inv:vip", "outdoor_inv:pub"):
            try:
                await redis.delete(key)
            except Exception:
                pass
