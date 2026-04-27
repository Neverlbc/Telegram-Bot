"""Google Sheets 库存查询服务.

从公开的 Google Sheets 中拉取实时库存数据。
Bot 展示表结构：SKU | QTYS | state | Notes
内部同步表结构：SKU | QTYS | 在途库存
仅返回 QTYS >= 0 的条目 (state = Available)。

使用 Redis 缓存 5 分钟，减少频繁请求。
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
from dataclasses import dataclass

import aiohttp
from redis.asyncio import Redis

from bot.config import settings
from bot.services.sku_mapping import get_stock_qty, resolve_skus, service_query_skus

logger = logging.getLogger(__name__)

IN_STOCK_STATE = "有货"
OUT_OF_STOCK_STATE = "None"
OUT_OF_STOCK_NOTE = "Для получения более подробной информации, пожалуйста, свяжитесь со службой поддержки клиентов."
AUTO_CLEAR_NOTES = frozenset(
    note.casefold()
    for note in (
        "在途中",
        "正在运输途中",
        "运输中",
        "None",
        OUT_OF_STOCK_NOTE,
    )
)


def clean_note_for_in_stock(note: str) -> str:
    """库存大于 0 时清理自动备注，保留其他人工描述."""
    cleaned = note.strip()
    if not cleaned:
        return ""
    if cleaned.casefold() == "none":
        return ""

    cleaned = cleaned.replace(OUT_OF_STOCK_NOTE, "")
    for fragment in ("正在运输途中", "在途中", "运输中"):
        cleaned = cleaned.replace(fragment, "")
    return cleaned.strip(" \t\r\n,，;；/|")


def should_clear_auto_note(note: str) -> bool:
    """库存恢复后是否应清理该自动备注."""
    value = note.strip()
    return bool(value) and (value.casefold() in AUTO_CLEAR_NOTES or clean_note_for_in_stock(value) != value)


def state_for_stock(qty: int) -> str:
    """按库存数量生成写回 Google Sheets 的 State."""
    return IN_STOCK_STATE if qty > 0 else OUT_OF_STOCK_STATE


def notes_for_stock(qty: int, current_note: str = "") -> str:
    """按库存数量生成写回 Google Sheets 的 Notes."""
    note = current_note.strip()
    if qty <= 0:
        return OUT_OF_STOCK_NOTE
    return clean_note_for_in_stock(note)


# Google Sheets CSV 导出基础 URL
SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d"
    "/{sheet_id}/export?format=csv&gid={gid}"
)

# 缓存时间（秒）
CACHE_TTL = 300  # 5 分钟

# 你的 Google Sheets ID
SHEET_ID = "1dSoCZE3gEp9G2lwoUIHxsX4Qf9m65NHwnL5yMDA08hY"

_redis_client: Redis | None = None


def get_redis_client() -> Redis | None:
    """获取共用的 Redis 客户端."""
    global _redis_client
    if _redis_client is None and settings.redis_host:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


@dataclass
class InventoryItem:
    """单个库存条目."""

    sku: str
    qty: int        # Google Sheets QTYS（聚水潭库存代理）
    state: str = ""
    notes: str = ""
    kyb_qty: int = 0  # KYB tocUsableQty（跨运宝已入俄仓数量）

    @property
    def net_qty(self) -> int:
        """实际可售数量 = 聚水潭 - 跨运宝（最小为 0）."""
        return max(0, self.qty - self.kyb_qty)

    @property
    def is_available(self) -> bool:
        return self.net_qty > 0

    def get_display_state(self, lang: str = "zh") -> str:
        """获取展示用库存状态: qty > 0 有货, qty == 0 缺货."""
        if self.qty > 0:
            labels = {
                "zh": "有货",
                "en": "Available",
                "ru": "В наличии",
            }
            return labels.get(lang, labels["zh"])

        labels = {
            "zh": "缺货",
            "en": "Out of stock",
            "ru": "распродано",
        }
        return labels.get(lang, labels["zh"])

    def get_display_notes(self, lang: str = "zh") -> str:
        """获取展示用备注."""
        note = self.notes.strip()
        if self.qty > 0:
            return clean_note_for_in_stock(note)
        if note:
            return note

        if self.qty == 0:
            labels = {
                "zh": OUT_OF_STOCK_NOTE,
                "en": OUT_OF_STOCK_NOTE,
                "ru": OUT_OF_STOCK_NOTE,
            }
            return labels.get(lang, labels["zh"])

        return ""

    def _normalize_state(self, lang: str) -> str:
        """将常见状态值归一到当前语言."""
        raw_state = self.state.strip()
        if not raw_state:
            return ""

        key = raw_state.casefold()
        state_map = {
            "available": {"zh": "有货", "en": "Available", "ru": "В наличии"},
            "in stock": {"zh": "有货", "en": "In stock", "ru": "В наличии"},
            "instock": {"zh": "有货", "en": "In stock", "ru": "В наличии"},
            "有货": {"zh": "有货", "en": "In stock", "ru": "В наличии"},
            "в наличии": {"zh": "有货", "en": "In stock", "ru": "В наличии"},
            "out of stock": {"zh": "缺货", "en": "Out of stock", "ru": "распродано"},
            "缺货": {"zh": "缺货", "en": "Out of stock", "ru": "распродано"},
            "нет в наличии": {"zh": "缺货", "en": "Out of stock", "ru": "распродано"},
            "распродано": {"zh": "缺货", "en": "Out of stock", "ru": "распродано"},
            "in transit": {"zh": "运输中", "en": "In transit", "ru": "В пути"},
            "运输中": {"zh": "运输中", "en": "In transit", "ru": "В пути"},
            "в пути": {"zh": "运输中", "en": "In transit", "ru": "В пути"},
        }

        labels = state_map.get(key)
        if labels:
            return labels.get(lang, labels["zh"])
        return raw_state

    def format_display(self) -> str:
        """格式化为展示文本，直接使用 qty（QTYS 已是最终显示数）."""
        note_part = f"\n   📝 {self.notes}" if self.notes.strip() else ""
        return f"• <b>{self.sku}</b>  ×{self.qty}{note_part}"


# ── Sheet 配置表 ────────────────────────────────────────
# 格式：{ "内部key": { "gid": GID, "name_*": 显示名称 } }
# 库存同步会遍历这里的全部 Sheet；Bot 商品目录只展示 TOP_CATEGORIES 中引用的 Sheet。
SHEET_CONFIG: dict[str, dict[str, str | int | bool]] = {
    "thermal_industrial": {
        "gid": 1141807238,
        "name_zh": "🏭 工业",
        "name_en": "🏭 Industrial",
        "name_ru": "🏭 Промышленные",
        "parent": "thermal",
    },
    "thermal_hunting": {
        "gid": 0,
        "name_zh": "🎯 狩猎",
        "name_en": "🎯 Hunting",
        "name_ru": "🎯 Охота",
        "parent": "thermal",
    },
    "thermal_special": {
        "gid": 986318582,
        "name_zh": "⭐ 特殊",
        "name_en": "⭐ Special",
        "name_ru": "⭐ Специальные",
        "parent": "thermal",
    },
    "power_tools": {
        "gid": 850367314,
        "name_zh": "🔧 动力工具",
        "name_en": "🔧 Power Tools",
        "name_ru": "🔧 Инструменты",
        "parent": "power",
    },
    "thermal_internal": {
        "gid": 1443225960,
        "name_zh": "热成像仪",
        "name_en": "Thermal Imager Internal",
        "name_ru": "Тепловизор внутренний",
        "internal_only": True,
    },
    "dewalt_internal": {
        "gid": 1855099112,
        "name_zh": "得伟",
        "name_en": "DeWalt Internal",
        "name_ru": "DeWalt внутренний",
        "internal_only": True,
    },
}

# 顶级分类定义
TOP_CATEGORIES: dict[str, dict] = {
    "thermal": {
        "name_zh": "🌡 热成像仪",
        "name_en": "🌡 Thermal Imager",
        "name_ru": "🌡 Тепловизор",
        "children": ["thermal_industrial", "thermal_hunting", "thermal_special"],
        "leaf": False,
    },
    "power": {
        "name_zh": "⚡ 动力工具",
        "name_en": "⚡ Power Tools",
        "name_ru": "⚡ Инструменты",
        "children": ["power_tools"],
        "leaf": True,   # 直接跳到库存，无子分类
    },
}


def is_internal_sheet(sheet_key: str) -> bool:
    """是否为仅内部库存同步使用的 Sheet."""
    return bool(SHEET_CONFIG.get(sheet_key, {}).get("internal_only"))


async def _fetch_csv(gid: int, session: aiohttp.ClientSession) -> str:
    """从 Google Sheets 下载指定 Sheet 的 CSV 内容."""
    url = SHEETS_CSV_URL.format(sheet_id=SHEET_ID, gid=gid)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        resp.raise_for_status()
        return await resp.text(encoding="utf-8")


def _fetch_csv_with_gspread_sync(gid: int) -> str:
    """使用 Service Account 读取非公开 Sheet，并转为 CSV 文本."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError("请先安装依赖：pip install gspread google-auth")

    creds_file = settings.google_credentials_file
    if not os.path.exists(creds_file):
        raise FileNotFoundError(f"Google Service Account JSON 不存在: {creds_file}")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    worksheet = None
    for ws in sh.worksheets():
        if ws.id == gid:
            worksheet = ws
            break
    if worksheet is None:
        raise ValueError(f"找不到 GID={gid} 的 worksheet")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(worksheet.get_all_values())
    return output.getvalue()


async def _fetch_csv_with_gspread(gid: int) -> str:
    """异步包装认证读取，避免阻塞事件循环."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_csv_with_gspread_sync, gid)


def _looks_like_sku(value: str) -> bool:
    """过滤内部表里的分组标题行，只保留看起来像 SKU 的行."""
    if not value:
        return False
    return any(char.isdigit() for char in value) or "-" in value or "+" in value


def _parse_csv(csv_text: str, sheet_key: str = "") -> list[InventoryItem]:
    """解析 CSV 文本，返回可用库存列表.

    规则：
    - 跳过表头行（第一行）
    - 只返回 QTYS >= 0 的条目
    - Notes 列可选
    """
    items: list[InventoryItem] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    internal = is_internal_sheet(sheet_key)
    for row in reader:
        sku = row.get("SKU", "").strip()
        if not sku:
            continue
        if internal and not _looks_like_sku(sku):
            continue
        try:
            qty = int(row.get("QTYS", "0").strip() or "0")
        except ValueError:
            qty = 0
        state = row.get("State", row.get("state", "")).strip()
        notes = row.get("Notes", "").strip()
        if qty >= 0:
            items.append(InventoryItem(sku=sku, qty=qty, state=state, notes=notes))
    return items


async def get_inventory(
    sheet_key: str,
) -> list[InventoryItem]:
    """获取指定分类的库存列表.

    先查 Redis 缓存；缓存未命中则从 Google Sheets 拉取。

    Args:
        sheet_key: SHEET_CONFIG 中的 key，如 "thermal_industrial"

    Returns:
        可用库存条目列表（qty >= 0）
    """
    config = SHEET_CONFIG.get(sheet_key)
    if not config:
        logger.warning("Unknown sheet_key: %s", sheet_key)
        return []

    gid = int(config["gid"])
    cache_key = f"inventory:{sheet_key}:{gid}"
    redis = get_redis_client()

    # ── 尝试读取缓存 ──────────────────────────────────
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("Cache hit: %s", cache_key)
                return _parse_csv(cached, sheet_key)
        except Exception as e:
            logger.warning("Redis cache read failed: %s", e)

    # ── 从 Google Sheets 拉取 ─────────────────────────
    try:
        async with aiohttp.ClientSession() as http:
            csv_text = await _fetch_csv(gid, http)
    except Exception as e:
        logger.warning("Public CSV fetch failed for %s (gid=%d), trying service account: %s", sheet_key, gid, e)
        try:
            csv_text = await _fetch_csv_with_gspread(gid)
        except Exception as auth_error:
            logger.error("Failed to fetch sheet %s (gid=%d): %s", sheet_key, gid, auth_error)
            return []

    items = _parse_csv(csv_text, sheet_key)

    # ── 写入缓存 ──────────────────────────────────────
    if redis is not None:
        try:
            await redis.set(cache_key, csv_text, ex=CACHE_TTL)
            logger.debug("Cache set: %s (TTL=%ds)", cache_key, CACHE_TTL)
        except Exception as e:
            logger.warning("Redis cache write failed: %s", e)

    return items


KYB_STOCK_CACHE_TTL = 300  # 5 分钟


async def get_inventory_with_kyb(sheet_key: str) -> list[InventoryItem]:
    """获取库存并叠加 KYB 数据，计算实际可售数量.

    net_qty = Google Sheets QTYS - KYB tocUsableQty（跨仓汇总）
    KYB 查询结果单独缓存 5 分钟，避免频繁调用。
    若 KYB 查询失败则降级为仅展示 Google Sheets 数据。
    """
    from bot.services.kuayunbao import kuayunbao_client

    items = await get_inventory(sheet_key)
    if not items:
        return items

    # ── 尝试从 Redis 读取 KYB 缓存 ────────────────────
    redis = get_redis_client()
    cache_key = f"kyb_stock:{sheet_key}"
    kyb_map: dict[str, int] = {}

    if redis is not None:
        try:
            import json as _json
            cached = await redis.get(cache_key)
            if cached:
                kyb_map = _json.loads(cached)
                logger.debug("KYB cache hit: %s", cache_key)
        except Exception as e:
            logger.warning("KYB cache read failed: %s", e)

    # ── 缓存未命中，实时查 KYB ──────────────────────────
    if not kyb_map and kuayunbao_client.is_configured:
        sku_lookups = resolve_skus(item.sku for item in items)
        skus = service_query_skus(sku_lookups.values(), "kyb")
        try:
            kyb_map = await kuayunbao_client.get_stock_map(skus)
        except Exception as e:
            logger.error("KYB stock_map query failed for %s: %s", sheet_key, e)

        if kyb_map and redis is not None:
            try:
                import json as _json
                await redis.set(cache_key, _json.dumps(kyb_map), ex=KYB_STOCK_CACHE_TTL)
            except Exception as e:
                logger.warning("KYB cache write failed: %s", e)

    # ── 合并 KYB 数量到每个 InventoryItem ─────────────
    sku_lookups = resolve_skus(item.sku for item in items)
    for item in items:
        item.kyb_qty = get_stock_qty(kyb_map, sku_lookups[item.sku].kyb_skus)

    return items


def get_sheet_name(sheet_key: str, lang: str = "zh") -> str:
    """获取分类的多语言名称."""
    config = SHEET_CONFIG.get(sheet_key, {})
    return config.get(f"name_{lang}", config.get("name_zh", sheet_key))


def get_category_name(cat_key: str, lang: str = "zh") -> str:
    """获取顶级分类的多语言名称."""
    config = TOP_CATEGORIES.get(cat_key, {})
    return config.get(f"name_{lang}", config.get("name_zh", cat_key))
