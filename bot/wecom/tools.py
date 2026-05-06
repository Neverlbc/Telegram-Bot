"""LLM 可调用的工具函数（库存、日报等）。

每个 tool 返回纯文本结果（不超过 4000 字符以内），方便企业微信发送。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select

from bot.models import async_session
from bot.models.analytics import AnalyticsEvent
from bot.services.outdoor_sheets import OutdoorItem, get_outdoor_inventory
from bot.services.service_center_sheet import get_repair_status, get_repair_status_by_sn
from bot.services.sn_sheet import search_sn

logger = logging.getLogger(__name__)

MAX_TEXT_LEN = 3500  # 企业微信文本上限 4096 字符；留点余量

# ── 工具实现 ────────────────────────────────────────────────


async def tool_get_inventory(tier: str = "vip") -> str:
    """读取莫斯科户外库存清单，返回多行文本（按品牌分组）。

    tier: public / vip / svip / vvip
    """
    tier_norm = (tier or "vip").lower()
    if tier_norm not in {"public", "vip", "svip", "vvip"}:
        tier_norm = "vip"

    try:
        items = await get_outdoor_inventory(vip=(tier_norm != "public"), tier=tier_norm)
    except Exception as exc:
        logger.exception("tool_get_inventory failed")
        return f"❌ 读取库存失败：{exc}"

    if not items:
        return "📭 当前没有可展示的库存数据。"

    return _format_inventory_text(items, tier_norm)


def _format_inventory_text(items: list[OutdoorItem], tier: str) -> str:
    tier_label = {"public": "普通", "vip": "VIP", "svip": "SVIP", "vvip": "VVIP"}.get(tier, tier.upper())
    available = [i for i in items if i.qty > 0]

    grouped: dict[str, list[OutdoorItem]] = {}
    for item in available:
        grouped.setdefault(item.brand or "其他", []).append(item)

    lines = [f"📦 莫斯科 · {tier_label} 库存（共 {len(available)} 个有货 SKU / {len(items)} 总）", ""]
    for brand, brand_items in grouped.items():
        lines.append(f"【{brand}】")
        for item in brand_items:
            lines.append(f"  {item.sku}  ×{item.qty}")
        lines.append("")

    text = "\n".join(lines).rstrip()
    if len(text) > MAX_TEXT_LEN:
        text = text[: MAX_TEXT_LEN - 30] + f"\n…（已截断，共 {len(items)} 行）"
    return text


async def tool_get_daily_report(period_days: int = 1) -> str:
    """生成最近 N 天的埋点日报（默认 1 天 = 今天）。

    包含：总事件、活跃用户、新增用户、按钮点击、价格查询、Top3 模块、Top3 动作。
    """
    today = date.today()
    since = datetime.combine(today - timedelta(days=period_days - 1), time.min)
    until = datetime.combine(today + timedelta(days=1), time.min)
    label = "今天" if period_days == 1 else f"近 {period_days} 天"

    try:
        async with async_session() as session:
            total_events = int(await session.scalar(
                select(func.count(AnalyticsEvent.id)).where(
                    AnalyticsEvent.created_at >= since,
                    AnalyticsEvent.created_at < until,
                )
            ) or 0)
            active_users = int(await session.scalar(
                select(func.count(func.distinct(AnalyticsEvent.telegram_id))).where(
                    AnalyticsEvent.created_at >= since,
                    AnalyticsEvent.created_at < until,
                    AnalyticsEvent.telegram_id.is_not(None),
                )
            ) or 0)
            callbacks = int(await session.scalar(
                select(func.count(AnalyticsEvent.id)).where(
                    AnalyticsEvent.created_at >= since,
                    AnalyticsEvent.created_at < until,
                    AnalyticsEvent.event_type == "callback",
                )
            ) or 0)
            price_queries = int(await session.scalar(
                select(func.count(AnalyticsEvent.id)).where(
                    AnalyticsEvent.created_at >= since,
                    AnalyticsEvent.created_at < until,
                    AnalyticsEvent.module == "inventory",
                    AnalyticsEvent.action.in_(("price_brands", "price_brand", "price_table", "price_images")),
                )
            ) or 0)

            # 新增用户：first_seen 在窗口内的 telegram_id 数
            first_seen_sub = (
                select(
                    AnalyticsEvent.telegram_id,
                    func.min(AnalyticsEvent.created_at).label("first_seen"),
                )
                .where(AnalyticsEvent.telegram_id.is_not(None))
                .group_by(AnalyticsEvent.telegram_id)
            ).subquery()
            new_users = int(await session.scalar(
                select(func.count(first_seen_sub.c.telegram_id)).where(
                    first_seen_sub.c.first_seen >= since,
                    first_seen_sub.c.first_seen < until,
                )
            ) or 0)

            # Top 3 模块
            module_stmt = (
                select(
                    func.coalesce(AnalyticsEvent.module, "unknown").label("module"),
                    func.count(AnalyticsEvent.id).label("c"),
                )
                .where(
                    AnalyticsEvent.created_at >= since,
                    AnalyticsEvent.created_at < until,
                )
                .group_by("module")
                .order_by(func.count(AnalyticsEvent.id).desc())
                .limit(3)
            )
            top_modules = [(r["module"], int(r["c"])) for r in (await session.execute(module_stmt)).mappings()]

            # Top 3 动作
            action_stmt = (
                select(
                    AnalyticsEvent.module,
                    AnalyticsEvent.action,
                    func.count(AnalyticsEvent.id).label("c"),
                )
                .where(
                    AnalyticsEvent.created_at >= since,
                    AnalyticsEvent.created_at < until,
                )
                .group_by(AnalyticsEvent.module, AnalyticsEvent.action)
                .order_by(func.count(AnalyticsEvent.id).desc())
                .limit(3)
            )
            top_actions = [
                (str(m or "unknown"), str(a or "unknown"), int(c))
                for m, a, c in (await session.execute(action_stmt))
            ]
    except Exception as exc:
        logger.exception("tool_get_daily_report failed")
        return f"❌ 生成日报失败：{exc}"

    lines = [
        f"📊 A-BF Bot 日报 · {label}（{since.date()} ~ {(until - timedelta(seconds=1)).date()}）",
        "",
        f"• 总事件：{total_events}",
        f"• 活跃用户：{active_users}",
        f"• 新增用户：{new_users}",
        f"• 按钮点击：{callbacks}",
        f"• 价格查询：{price_queries}",
        "",
    ]
    if top_modules:
        lines.append("Top 模块：")
        for mod, cnt in top_modules:
            lines.append(f"  {_module_label(mod)} — {cnt}")
        lines.append("")
    if top_actions:
        lines.append("Top 动作：")
        for mod, act, cnt in top_actions:
            lines.append(f"  {_module_label(mod)}：{act} — {cnt}")

    return "\n".join(lines).rstrip()


async def tool_search_sn(sn: str) -> str:
    """在跨品牌 SN 数据库中查找序列号，确认设备是否由 A-BF 供货。"""
    q = (sn or "").strip()
    if not q:
        return "❌ 请提供序列号。"
    try:
        records = await search_sn(q)
    except Exception as exc:
        logger.exception("tool_search_sn failed")
        return f"❌ 查询序列号失败：{exc}"

    if not records:
        return f"❌ 数据库中未找到序列号 {q.upper()}。该设备可能不是由 A-BF 供货，或序列号有误。"

    lines = [f"✅ 找到序列号 {q.upper()}，设备由 A-BF 供货：", ""]
    for r in records:
        lines.append(f"品牌：{r.brand}")
        lines.append(f"型号：{r.model}")
        lines.append(f"序列号：{r.sn}")
        if r.notes and r.notes.lower() not in ("", "notes"):
            lines.append(f"备注：{r.notes}")
        lines.append("")
    return "\n".join(lines).rstrip()


async def tool_check_repair(query: str) -> str:
    """根据 CDEK 快递单号或 SN 序列号查询俄罗斯服务中心检修状态。"""
    q = (query or "").strip()
    if not q:
        return "❌ 请提供 CDEK 单号或设备序列号。"
    try:
        record = await get_repair_status(q)
        if record is None:
            record = await get_repair_status_by_sn(q)
    except Exception as exc:
        logger.exception("tool_check_repair failed")
        return f"❌ 查询检修状态失败：{exc}"

    if record is None:
        return f"❌ 未找到 {q} 的检修记录（已查 CDEK 单号和序列号）。"

    emoji = record.status_emoji()
    lines = [f"{emoji} 检修记录", ""]
    if record.cdek_in:
        lines.append(f"CDEK 入库单号：{record.cdek_in}")
    if record.sn:
        lines.append(f"序列号：{record.sn}")
    if record.model:
        lines.append(f"型号：{record.model}")
    lines.append(f"状态：{record.status}")
    if record.cdek_out:
        lines.append(f"回寄单号：{record.cdek_out}")
    if record.repair_summary:
        lines.append(f"维修报告：{record.repair_summary}")
    if record.notes:
        lines.append(f"备注：{record.notes}")
    return "\n".join(lines)


def _module_label(code: str) -> str:
    mapping = {
        "menu": "主菜单",
        "hidden_access": "隐藏入口",
        "inventory": "莫斯科现货库存",
        "language": "语言切换",
        "navigation": "导航",
        "service_center": "服务中心",
        "vandych": "Vandych",
        "command": "命令",
        "message": "普通消息",
        "callback": "按钮点击",
    }
    return mapping.get(code, code)


# ── DeepSeek function-calling 用的 schema 描述 ───────────────


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": (
                "查询莫斯科仓库的户外类现货库存清单。"
                "返回按品牌分组的 SKU 列表与对应数量。"
                "当用户问「库存」「现货」「莫斯科有什么」「stock」「inventory」之类时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tier": {
                        "type": "string",
                        "enum": ["public", "vip", "svip", "vvip"],
                        "description": "查询的权限层级。默认 vip 给内部员工；public 只看公开 SKU。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_report",
            "description": (
                "生成 Telegram Bot 用户埋点日报：总事件 / 活跃用户 / 新增用户 / 点击 / "
                "价格查询次数 + Top 模块和动作。"
                "当用户问「日报」「今日数据」「机器人怎么样了」「报告」「statistics」之类时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period_days": {
                        "type": "integer",
                        "description": "覆盖天数：1=今天（默认）、7=近 7 天、30=近 30 天",
                        "minimum": 1,
                        "maximum": 90,
                    },
                },
                "required": [],
            },
        },
    },
]


TOOL_SCHEMAS += [
    {
        "type": "function",
        "function": {
            "name": "search_sn",
            "description": (
                "在 A-BF 设备数据库中查询序列号（SN），确认该设备是否由我司供货。"
                "支持 Infiray、Sytong、Longot、NNPO、Pard、Airsoft、DNT 等品牌。"
                "当用户提供 SN / 序列号并询问设备来源、真假验证时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sn": {
                        "type": "string",
                        "description": "设备序列号，原样传入（不区分大小写）",
                    },
                },
                "required": ["sn"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_repair",
            "description": (
                "查询俄罗斯服务中心的设备检修/维修状态。"
                "支持用 CDEK 快递单号或 SN 序列号查询。"
                "当用户询问「检修」「维修状态」「CDEK」「修好了吗」等时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "CDEK 快递单号或 SN 序列号",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "get_inventory": tool_get_inventory,
    "get_daily_report": tool_get_daily_report,
    "search_sn": tool_search_sn,
    "check_repair": tool_check_repair,
}
