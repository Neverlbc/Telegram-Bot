"""莫斯科户外现货 Google Sheets 服务.

从用户提供的 Google Sheet 读取户外类库存。
表格结构（列名由配置决定）：
  SKU | 型号/名称 | 数量 | 是否展示(1=公开, 0=VIP专属) | 备注

VIP 用户可见全部行，普通用户只见 is_public == True 的行。
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field

import aiohttp
from redis.asyncio import Redis

from bot.config import settings

logger = logging.getLogger(__name__)

SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d"
    "/{sheet_id}/export?format=csv&gid={gid}"
)
CACHE_TTL = 300  # 5 分钟

# 表头列名配置 — 与实际 Google Sheet 列名对应，如需调整在此处修改
COL_SKU = "SKU"
COL_NAME = "名称"        # 中文商品名
COL_QTY = "数量"         # 库存数量
COL_PUBLIC = "是否展示"  # 1 或 yes → 公开可见；0 或 no → VIP专属
COL_NOTES = "备注"

# Outdoor sheet 默认使用第一个 tab（gid=0），可扩展为多 tab
OUTDOOR_GID = 0

_redis_client: Redis | None = None


def _get_redis() -> Redis | None:
    global _redis_client
    if _redis_client is None and settings.redis_host:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


@dataclass
class OutdoorItem:
    sku: str
    name: str
    qty: int
    is_public: bool = True  # True = 公开可见, False = 仅 VIP 可见
    notes: str = ""

    @property
    def is_available(self) -> bool:
        return self.qty > 0

    def status_text(self, lang: str = "zh") -> str:
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
        try:
            qty = int(row.get(COL_QTY, "0").strip() or "0")
        except ValueError:
            qty = 0
        name = row.get(COL_NAME, sku).strip()
        notes = row.get(COL_NOTES, "").strip()
        raw_public = str(row.get(COL_PUBLIC, "1")).strip().lower()
        is_public = raw_public in ("1", "yes", "true", "是", "公开", "y")
        items.append(OutdoorItem(sku=sku, name=name, qty=qty, is_public=is_public, notes=notes))
    return items


async def get_outdoor_inventory(vip: bool = False) -> list[OutdoorItem]:
    """获取户外类库存列表.

    Args:
        vip: True 返回全部行（VIP 视图），False 只返回公开展示行。

    Returns:
        OutdoorItem 列表。Sheet ID 未配置时返回空列表。
    """
    sheet_id = settings.outdoor_sheet_id
    if not sheet_id:
        logger.warning("outdoor_sheet_id not configured")
        return []

    cache_key = f"outdoor_inv:{'vip' if vip else 'pub'}"
    redis = _get_redis()

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                items = _parse_csv(cached)
                return items if vip else [i for i in items if i.is_public]
        except Exception as e:
            logger.warning("Redis read failed: %s", e)

    url = SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=OUTDOOR_GID)
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
            # 全量缓存原始 CSV，两种视图共享同一缓存源
            await redis.set(cache_key, csv_text, ex=CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed: %s", e)

    items = _parse_csv(csv_text)
    return items if vip else [i for i in items if i.is_public]


async def clear_outdoor_cache() -> None:
    redis = _get_redis()
    if redis is not None:
        for key in ("outdoor_inv:vip", "outdoor_inv:pub"):
            try:
                await redis.delete(key)
            except Exception:
                pass
