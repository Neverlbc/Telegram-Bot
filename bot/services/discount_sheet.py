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
