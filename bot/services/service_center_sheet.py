"""A-BF 俄罗斯服务中心 Google Sheets 服务.

表格结构（列名由配置决定）：
  CDEK单号(寄件) | SN | 设备型号 | 检修状态 | 客户TGID | 回寄CDEK单号 | 备注

检修状态流转示例: 待检 → 检修中 → 完成 → 已寄回
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
CACHE_TTL = 120  # 2 分钟（状态查询需要更新鲜）

# 列名配置 — 与实际 Sheet 表头对应
COL_CDEK_IN = "寄件CDEK单号"     # 客户寄来的 CDEK 单号
COL_SN = "SN"
COL_MODEL = "型号"
COL_STATUS = "检修状态"
COL_CUSTOMER_TG = "客户TGID"     # 客户 Telegram 数字 ID
COL_CDEK_OUT = "回寄CDEK单号"    # 维修完成后回寄客户的单号
COL_NOTES = "备注"

SC_GID = 0  # 默认第一个 tab

_redis_client: Redis | None = None


def _get_redis() -> Redis | None:
    global _redis_client
    if _redis_client is None and settings.redis_host:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


@dataclass
class RepairRecord:
    cdek_in: str
    sn: str = ""
    model: str = ""
    status: str = ""
    customer_tg_id: str = ""
    cdek_out: str = ""    # 回寄单号，空 = 尚未寄回
    notes: str = ""

    def status_emoji(self) -> str:
        s = self.status.strip()
        if "完成" in s or "done" in s.lower() or "завершён" in s.lower():
            return "✅"
        if "中" in s or "progress" in s.lower() or "ремонт" in s.lower():
            return "🔧"
        if "回" in s or "shipped" in s.lower() or "отправлен" in s.lower():
            return "📦"
        return "⏳"


def _parse_csv(csv_text: str) -> list[RepairRecord]:
    records: list[RepairRecord] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        cdek_in = row.get(COL_CDEK_IN, "").strip()
        if not cdek_in:
            continue
        records.append(RepairRecord(
            cdek_in=cdek_in,
            sn=row.get(COL_SN, "").strip(),
            model=row.get(COL_MODEL, "").strip(),
            status=row.get(COL_STATUS, "").strip(),
            customer_tg_id=row.get(COL_CUSTOMER_TG, "").strip(),
            cdek_out=row.get(COL_CDEK_OUT, "").strip(),
            notes=row.get(COL_NOTES, "").strip(),
        ))
    return records


async def _fetch_all_records() -> list[RepairRecord]:
    sheet_id = settings.service_center_sheet_id
    if not sheet_id:
        logger.warning("service_center_sheet_id not configured")
        return []

    cache_key = "sc_records_csv"
    redis = _get_redis()

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return _parse_csv(cached)
        except Exception as e:
            logger.warning("Redis read failed: %s", e)

    url = SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=SC_GID)
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                csv_text = await resp.text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to fetch service center sheet: %s", e)
        return []

    if redis is not None:
        try:
            await redis.set(cache_key, csv_text, ex=CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed: %s", e)

    return _parse_csv(csv_text)


async def get_repair_status(cdek_no: str) -> RepairRecord | None:
    """根据 CDEK 单号查询检修状态."""
    records = await _fetch_all_records()
    cdek_no = cdek_no.strip().upper()
    for r in records:
        if r.cdek_in.upper() == cdek_no:
            return r
    return None


async def get_all_records() -> list[RepairRecord]:
    """管理员用：获取全部检修记录."""
    return await _fetch_all_records()


async def clear_cache() -> None:
    redis = _get_redis()
    if redis is not None:
        try:
            await redis.delete("sc_records_csv")
        except Exception:
            pass


# ── 状态监听 Redis 辅助函数 ──────────────────────────────

async def register_watcher(cdek_no: str, user_id: int, lang: str = "zh") -> None:
    """注册用户监听某个 CDEK 单号的状态变更，同时记录语言偏好."""
    redis = _get_redis()
    if redis is None:
        return
    key = f"sc_watch:{cdek_no.upper()}"
    lang_key = f"sc_watch_lang:{cdek_no.upper()}:{user_id}"
    try:
        await redis.sadd(key, str(user_id))
        await redis.expire(key, 86400 * 30)
        await redis.set(lang_key, lang, ex=86400 * 30)
    except Exception as e:
        logger.warning("register_watcher failed: %s", e)


async def get_watcher_lang(cdek_no: str, user_id: int) -> str:
    """获取监听用户的语言偏好，用于推送通知."""
    redis = _get_redis()
    if redis is None:
        return "zh"
    try:
        val = await redis.get(f"sc_watch_lang:{cdek_no.upper()}:{user_id}")
        return val or "zh"
    except Exception:
        return "zh"


async def get_watchers(cdek_no: str) -> list[int]:
    """获取监听指定 CDEK 单号的用户 ID 列表."""
    redis = _get_redis()
    if redis is None:
        return []
    key = f"sc_watch:{cdek_no.upper()}"
    try:
        members = await redis.smembers(key)
        return [int(m) for m in members]
    except Exception:
        return []


async def get_known_status(cdek_no: str) -> str:
    """从 Redis 获取上次已知的检修状态（用于变更检测）."""
    redis = _get_redis()
    if redis is None:
        return ""
    try:
        val = await redis.get(f"sc_status:{cdek_no.upper()}")
        return val or ""
    except Exception:
        return ""


async def set_known_status(cdek_no: str, status: str) -> None:
    """记录最新检修状态到 Redis."""
    redis = _get_redis()
    if redis is None:
        return
    try:
        await redis.set(f"sc_status:{cdek_no.upper()}", status, ex=86400 * 30)
    except Exception as e:
        logger.warning("set_known_status failed: %s", e)
