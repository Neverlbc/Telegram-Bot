"""Web dashboard for bot usage analytics.

Public dashboard endpoints (all support shared filter params):

    period            day|week|month|custom (default: week)
    start_date        YYYY-MM-DD (period=custom)
    end_date          YYYY-MM-DD (period=custom, inclusive)
    include_test      0/1, default 0 (exclude admin/test accounts)
    days              backwards-compat shortcut (1..90)

Endpoints:

    GET /                       HTML dashboard
    GET /health                 healthcheck
    GET /api/summary            top-level summary + classic widgets
    GET /api/heat?compare=...   module heat with previous-period comparison
    GET /api/trends             4-line trend (new/active/clicks/price queries)
    GET /api/tier-distribution  member tier breakdown
    GET /api/hidden-menu        hidden-menu activation metrics
    GET /api/export?type=...    xlsx export (actions|users|events|trends|hidden_menu)
    GET /api/annotations        list manual promo / activity annotations
    POST /api/annotations       create new annotation
    PUT /api/annotations/{id}   update annotation
    DELETE /api/annotations/{id} delete annotation
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from aiohttp import web
from sqlalchemy import and_, func, or_, select

from bot.config import settings
from bot.logging_config import setup_logging
from bot.models import async_session
from bot.models.analytics import AnalyticsEvent
from bot.models.analytics_annotation import AnalyticsAnnotation
from bot.models.user import User

logger = logging.getLogger(__name__)

# ── Label maps ─────────────────────────────────────────────

MODULE_LABELS = {
    "menu": "主菜单",
    "hidden_access": "隐藏入口",
    "inventory": "莫斯科现货库存",
    "language": "语言切换",
    "navigation": "导航",
    "service_center": "A-BF俄罗斯服务中心",
    "vandych": "Vandych的帐篷",
    "command": "命令",
    "message": "普通消息",
    "callback": "按钮点击",
    "unknown": "未知模块",
}

LANGUAGE_LABELS = {
    "zh": "中文",
    "en": "英文",
    "ru": "俄文",
    "unknown": "未知语言",
}

ACTION_LABELS = {
    "command.start": "启动 Bot",
    "command.menu": "打开主菜单",
    "command.cancel": "取消当前操作",
    "command.lang": "语言设置命令",
    "command.help": "查看帮助",
    "hidden_access.vip_inventory": "激活 VIP 库存隐藏菜单",
    "hidden_access.svip_inventory": "激活 SVIP 隐藏菜单",
    "hidden_access.vvip_inventory": "激活 VVIP 隐藏菜单",
    "hidden_access.service_admin": "激活服务中心隐藏菜单",
    "hidden_access.vandych": "激活 Vandych 专属菜单",
    "inventory.menu": "进入莫斯科现货查询",
    "inventory.tier_menu": "进入库存权限隐藏菜单",
    "inventory.public_query": "普通库存查询",
    "inventory.categories": "查看库存分类",
    "inventory.category": "进入户外库存分类",
    "inventory.quick": "快速展示有库存商品",
    "inventory.brand": "按品牌查看库存",
    "inventory.price_brands": "查看价格品牌列表",
    "inventory.price_brand": "查看品牌价格",
    "inventory.price_table": "查看价格表",
    "inventory.price_images": "查看价格图片",
    "language.zh": "切换语言：中文",
    "language.en": "切换语言：英文",
    "language.ru": "切换语言：俄文",
    "menu.settings": "进入设置",
    "menu.setting_lang": "设置中切换语言",
    "navigation.home": "返回主菜单",
    "navigation.back": "返回上级菜单",
    "service_center.menu": "进入服务中心",
    "service_center.info": "查看服务中心说明",
    "service_center.link": "打开服务中心频道链接",
    "service_center.repair": "设备检修查询",
    "service_center.admin_home": "进入服务中心隐藏后台",
    "service_center.admin_menu": "查看服务中心通知说明",
    "service_center.sn_list": "查看 SN 列表",
    "service_center.sn_search": "查询 SN 记录",
    "vandych.menu": "进入 Vandych 专属菜单",
    "vandych.discount": "获取折扣码和链接",
    "vandych.sku_select": "查看指定 SKU 折扣",
    "vandych.shipping": "查看空运支付链接",
    "vandych.wholesale": "提交批发需求",
    "message.text_message": "普通文本消息",
    "inventory.text_input": "库存模块文本输入",
    "service_center.text_input": "服务中心查询输入",
    "vandych.text_input": "Vandych 批发需求输入",
}

EVENT_NAME_LABELS = {
    "hidden_access.password_success": "隐藏菜单密码验证成功",
}

# Tier hierarchy (highest first) used for user classification
TIER_PRIORITY = ("vvip_inventory", "svip_inventory", "vip_inventory", "vandych", "service_admin")

TIER_LABELS = {
    "vvip_inventory": "VVIP",
    "svip_inventory": "SVIP",
    "vip_inventory": "VIP",
    "vandych": "Vandych",
    "service_admin": "服务管理员",
    "public": "普通",
}

TIER_DISPLAY_ORDER = ("public", "vip_inventory", "svip_inventory", "vvip_inventory", "vandych", "service_admin")

HIDDEN_MENU_LABELS = {
    "vip_inventory": "VIP 库存",
    "svip_inventory": "SVIP 库存",
    "vvip_inventory": "VVIP 库存",
    "service_admin": "服务中心管理后台",
    "vandych": "Vandych 隐藏菜单",
}

PRICE_QUERY_ACTIONS = ("price_brands", "price_brand", "price_table", "price_images")

# ── Filter / auth helpers ──────────────────────────────────


@dataclass
class QueryFilter:
    """Shared filter for analytics queries."""

    since: datetime
    until: datetime
    exclude_test_ids: list[int]
    period_label: str  # day/week/month/custom — for UI display

    def previous_window(self) -> "QueryFilter":
        """Return the same-length window immediately before this one."""
        delta = self.until - self.since
        return QueryFilter(
            since=self.since - delta,
            until=self.since,
            exclude_test_ids=self.exclude_test_ids,
            period_label=self.period_label,
        )

    def apply_time(self, stmt: Any) -> Any:
        return stmt.where(
            AnalyticsEvent.created_at >= self.since,
            AnalyticsEvent.created_at < self.until,
        )

    def apply_user(self, stmt: Any) -> Any:
        if not self.exclude_test_ids:
            return stmt
        return stmt.where(
            or_(
                AnalyticsEvent.telegram_id.is_(None),
                AnalyticsEvent.telegram_id.notin_(self.exclude_test_ids),
            )
        )

    def apply(self, stmt: Any) -> Any:
        return self.apply_user(self.apply_time(stmt))


def _parse_date(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return default


def _parse_filter(request: web.Request) -> QueryFilter:
    today = date.today()
    period = (request.query.get("period") or "").strip().lower()
    has_custom_dates = request.query.get("start_date") or request.query.get("end_date")

    if period == "custom" or has_custom_dates:
        start = _parse_date(request.query.get("start_date"), today - timedelta(days=6))
        end = _parse_date(request.query.get("end_date"), today)
        if end < start:
            start, end = end, start
        since = datetime.combine(start, time.min)
        until = datetime.combine(end + timedelta(days=1), time.min)
        period_label = "custom"
    elif period == "day":
        since = datetime.combine(today, time.min)
        until = datetime.combine(today + timedelta(days=1), time.min)
        period_label = "day"
    elif period == "week":
        since = datetime.combine(today - timedelta(days=6), time.min)
        until = datetime.combine(today + timedelta(days=1), time.min)
        period_label = "week"
    elif period == "month":
        since = datetime.combine(today - timedelta(days=29), time.min)
        until = datetime.combine(today + timedelta(days=1), time.min)
        period_label = "month"
    else:
        # Backwards-compat: days=N
        try:
            days = int(request.query.get("days", "7"))
        except ValueError:
            days = 7
        days = max(1, min(days, 90))
        since = datetime.combine(today - timedelta(days=days - 1), time.min)
        until = datetime.combine(today + timedelta(days=1), time.min)
        period_label = f"days{days}"

    include_test = (request.query.get("include_test", "") or "").strip().lower() in ("1", "true", "yes")
    exclude_ids = [] if include_test else list(settings.admin_id_list)

    return QueryFilter(
        since=since,
        until=until,
        exclude_test_ids=exclude_ids,
        period_label=period_label,
    )


def _json_error(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _authorized(request: web.Request) -> bool:
    expected = settings.analytics_dashboard_token.strip()
    if not expected:
        return True

    auth = request.headers.get("Authorization", "")
    bearer = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    provided = (
        request.query.get("token", "")
        or request.headers.get("X-Analytics-Token", "")
        or bearer
    ).strip()
    return provided == expected


def _dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def _event_outcome(event_data: Any) -> str | None:
    if isinstance(event_data, dict):
        value = event_data.get("outcome")
        return str(value) if value else None
    return None


def _module_label(module: Any) -> str:
    code = str(module or "unknown")
    return MODULE_LABELS.get(code, code)


def _language_label(language: Any) -> str:
    code = str(language or "unknown")
    return LANGUAGE_LABELS.get(code, code)


def _tier_label(code: Any) -> str:
    return TIER_LABELS.get(str(code or "public"), "普通")


def _hidden_menu_label(code: Any) -> str:
    return HIDDEN_MENU_LABELS.get(str(code or ""), str(code or "未知菜单"))


def _action_label(module: Any, action: Any, event_name: Any = None, event_data: Any = None) -> str:
    module_code = str(module or "unknown")
    action_code = str(action or "unknown")
    key = f"{module_code}.{action_code}"

    if module_code == "hidden_access" and isinstance(event_data, dict):
        kind = event_data.get("kind")
        if kind:
            key = f"hidden_access.{kind}"

    if key in ACTION_LABELS:
        return ACTION_LABELS[key]

    event_key = str(event_name or "")
    if event_key in EVENT_NAME_LABELS:
        return EVENT_NAME_LABELS[event_key]

    module_label = _module_label(module_code)
    return f"{module_label}：{action_code}"


# ── User tier classification ────────────────────────────────


async def _get_user_tiers(session: Any, telegram_ids: list[int]) -> dict[int, str]:
    """Return {telegram_id: highest_tier_code} for users who have unlocked hidden menus.

    Looks at all-time hidden_access password_success events. Tier hierarchy:
      vvip > svip > vip > vandych > service_admin > (default public, not in map)
    """
    if not telegram_ids:
        return {}

    stmt = select(AnalyticsEvent.telegram_id, AnalyticsEvent.event_data).where(
        AnalyticsEvent.telegram_id.in_(telegram_ids),
        AnalyticsEvent.event_name == "hidden_access.password_success",
    )
    result = await session.execute(stmt)

    user_kinds: dict[int, set[str]] = {}
    for telegram_id, event_data in result:
        if not telegram_id or not isinstance(event_data, dict):
            continue
        kind = event_data.get("kind")
        if kind:
            user_kinds.setdefault(telegram_id, set()).add(str(kind))

    tier_map: dict[int, str] = {}
    for tid, kinds in user_kinds.items():
        for tier in TIER_PRIORITY:
            if tier in kinds:
                tier_map[tid] = tier
                break
    return tier_map


# ── Query helpers (with filter) ─────────────────────────────


async def _scalar(session: Any, stmt: Any) -> int:
    value = await session.scalar(stmt)
    return int(value or 0)


async def _summary_counts(session: Any, qf: QueryFilter) -> dict[str, int]:
    base = select(func.count(AnalyticsEvent.id))
    callbacks_stmt = qf.apply(base.where(AnalyticsEvent.event_type == "callback"))
    messages_stmt = qf.apply(base.where(AnalyticsEvent.event_type == "message"))
    total_stmt = qf.apply(base)

    user_stmt = qf.apply(
        select(func.count(func.distinct(AnalyticsEvent.telegram_id))).where(
            AnalyticsEvent.telegram_id.is_not(None)
        )
    )

    recent_since = datetime.utcnow() - timedelta(minutes=15)
    recent_stmt = select(func.count(func.distinct(AnalyticsEvent.telegram_id))).where(
        AnalyticsEvent.telegram_id.is_not(None),
        AnalyticsEvent.created_at >= recent_since,
    )
    if qf.exclude_test_ids:
        recent_stmt = recent_stmt.where(
            AnalyticsEvent.telegram_id.notin_(qf.exclude_test_ids)
        )

    return {
        "total_events": await _scalar(session, total_stmt),
        "active_users": await _scalar(session, user_stmt),
        "callbacks": await _scalar(session, callbacks_stmt),
        "messages": await _scalar(session, messages_stmt),
        "recent_active_users": await _scalar(session, recent_stmt),
    }


async def _count_by(
    session: Any,
    qf: QueryFilter,
    column: Any,
    limit: int,
    label_fn: Any | None = None,
) -> list[dict[str, Any]]:
    name = func.coalesce(column, "unknown").label("name")
    count = func.count(AnalyticsEvent.id).label("count")
    stmt = qf.apply(select(name, count)).group_by(name).order_by(count.desc()).limit(limit)
    result = await session.execute(stmt)
    rows: list[dict[str, Any]] = []
    for row in result.mappings():
        code = str(row["name"])
        rows.append({
            "name": label_fn(code) if label_fn else code,
            "code": code,
            "count": int(row["count"]),
        })
    total = sum(row["count"] for row in rows) or 1
    for row in rows:
        row["percent"] = round(row["count"] * 100 / total, 2)
    return rows


async def _top_actions(session: Any, qf: QueryFilter, limit: int = 16) -> list[dict[str, Any]]:
    count = func.count(AnalyticsEvent.id).label("count")
    distinct_users = func.count(func.distinct(AnalyticsEvent.telegram_id)).label("users")
    stmt = (
        qf.apply(select(AnalyticsEvent.module, AnalyticsEvent.action, count, distinct_users))
        .group_by(AnalyticsEvent.module, AnalyticsEvent.action)
        .order_by(count.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows: list[dict[str, Any]] = []
    for module, action, event_count, user_count in result:
        module_code = str(module or "unknown")
        action_code = str(action or "unknown")
        rows.append({
            "name": _action_label(module_code, action_code),
            "code": f"{module_code}.{action_code}",
            "count": int(event_count),
            "users": int(user_count or 0),
        })
    total = sum(row["count"] for row in rows) or 1
    for row in rows:
        row["percent"] = round(row["count"] * 100 / total, 2)
    return rows


async def _module_heat(session: Any, qf: QueryFilter) -> list[dict[str, Any]]:
    """Module heat with previous-period comparison."""
    current = await _module_heat_window(session, qf)
    prev_qf = qf.previous_window()
    previous = await _module_heat_window(session, prev_qf)
    prev_map = {row["code"]: row for row in previous}

    rows: list[dict[str, Any]] = []
    for row in current:
        prev_row = prev_map.get(row["code"], {})
        prev_count = int(prev_row.get("count", 0) or 0)
        prev_users = int(prev_row.get("users", 0) or 0)
        delta = row["count"] - prev_count
        delta_pct = (delta / prev_count * 100) if prev_count else (100.0 if row["count"] else 0.0)
        rows.append({
            **row,
            "previous_count": prev_count,
            "previous_users": prev_users,
            "delta": delta,
            "delta_percent": round(delta_pct, 2),
        })
    return rows


async def _module_heat_window(session: Any, qf: QueryFilter) -> list[dict[str, Any]]:
    name = func.coalesce(AnalyticsEvent.module, "unknown").label("module")
    count = func.count(AnalyticsEvent.id).label("count")
    users = func.count(func.distinct(AnalyticsEvent.telegram_id)).label("users")
    stmt = qf.apply(select(name, count, users)).group_by(name).order_by(count.desc())
    result = await session.execute(stmt)
    rows: list[dict[str, Any]] = []
    for row in result.mappings():
        code = str(row["module"])
        rows.append({
            "code": code,
            "name": _module_label(code),
            "count": int(row["count"]),
            "users": int(row["users"] or 0),
        })
    total = sum(row["count"] for row in rows) or 1
    for row in rows:
        row["percent"] = round(row["count"] * 100 / total, 2)
    return rows


async def _daily_trends(session: Any, qf: QueryFilter) -> list[dict[str, Any]]:
    """Per-day metrics: events, active users, callbacks, price queries, plus new users."""
    day_col = func.date(AnalyticsEvent.created_at).label("day")

    # 1) Total events + active users per day
    base_stmt = qf.apply(
        select(
            day_col,
            func.count(AnalyticsEvent.id).label("events"),
            func.count(func.distinct(AnalyticsEvent.telegram_id)).label("users"),
        )
    ).group_by(day_col).order_by(day_col)
    events_by_day = {
        str(r["day"]): {"events": int(r["events"]), "users": int(r["users"])}
        for r in (await session.execute(base_stmt)).mappings()
    }

    # 2) Callbacks per day
    cb_stmt = qf.apply(
        select(day_col, func.count(AnalyticsEvent.id).label("c"))
        .where(AnalyticsEvent.event_type == "callback")
    ).group_by(day_col)
    callbacks_by_day = {str(r["day"]): int(r["c"]) for r in (await session.execute(cb_stmt)).mappings()}

    # 3) Price queries per day
    price_stmt = qf.apply(
        select(day_col, func.count(AnalyticsEvent.id).label("c"))
        .where(
            AnalyticsEvent.module == "inventory",
            AnalyticsEvent.action.in_(PRICE_QUERY_ACTIONS),
        )
    ).group_by(day_col)
    price_by_day = {str(r["day"]): int(r["c"]) for r in (await session.execute(price_stmt)).mappings()}

    # 4) New users per day (first-ever event for each user falls within window)
    first_event_stmt = (
        select(
            AnalyticsEvent.telegram_id,
            func.min(AnalyticsEvent.created_at).label("first_seen"),
        )
        .where(AnalyticsEvent.telegram_id.is_not(None))
        .group_by(AnalyticsEvent.telegram_id)
    ).subquery()

    new_users_stmt = (
        select(
            func.date(first_event_stmt.c.first_seen).label("day"),
            func.count(first_event_stmt.c.telegram_id).label("c"),
        )
        .where(
            first_event_stmt.c.first_seen >= qf.since,
            first_event_stmt.c.first_seen < qf.until,
        )
        .group_by(func.date(first_event_stmt.c.first_seen))
    )
    if qf.exclude_test_ids:
        new_users_stmt = new_users_stmt.where(
            first_event_stmt.c.telegram_id.notin_(qf.exclude_test_ids)
        )
    new_users_by_day = {
        str(r["day"]): int(r["c"])
        for r in (await session.execute(new_users_stmt)).mappings()
    }

    # Build day-by-day list
    rows: list[dict[str, Any]] = []
    cursor = qf.since.date()
    end = (qf.until - timedelta(seconds=1)).date()
    while cursor <= end:
        key = cursor.isoformat()
        base = events_by_day.get(key, {"events": 0, "users": 0})
        rows.append({
            "day": key,
            "events": base["events"],
            "active_users": base["users"],
            "callbacks": callbacks_by_day.get(key, 0),
            "price_queries": price_by_day.get(key, 0),
            "new_users": new_users_by_day.get(key, 0),
        })
        cursor += timedelta(days=1)
    return rows


async def _top_users(session: Any, qf: QueryFilter, limit: int = 30) -> list[dict[str, Any]]:
    count = func.count(AnalyticsEvent.id).label("count")
    last_seen = func.max(AnalyticsEvent.created_at).label("last_seen")
    stmt = (
        qf.apply(
            select(
                AnalyticsEvent.telegram_id,
                func.max(User.username).label("username"),
                func.max(User.first_name).label("first_name"),
                func.max(User.last_name).label("last_name"),
                func.max(AnalyticsEvent.language).label("language"),
                count,
                last_seen,
            ).where(AnalyticsEvent.telegram_id.is_not(None))
        )
        .outerjoin(User, User.telegram_id == AnalyticsEvent.telegram_id)
        .group_by(AnalyticsEvent.telegram_id)
        .order_by(count.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    user_rows = list(result.mappings())
    telegram_ids = [int(row["telegram_id"]) for row in user_rows if row["telegram_id"]]
    tier_map = await _get_user_tiers(session, telegram_ids)

    rows: list[dict[str, Any]] = []
    for row in user_rows:
        tid = row["telegram_id"]
        name_parts = [part for part in (row["first_name"], row["last_name"]) if part]
        display_name = (" ".join(name_parts) or row["username"] or str(tid))
        if row["username"]:
            display_name = f"{display_name} (@{row['username']})"
        tier_code = tier_map.get(int(tid) if tid else 0, "public")
        rows.append({
            "telegram_id": tid,
            "display_name": display_name,
            "language": row["language"] or "unknown",
            "tier_code": tier_code,
            "tier_label": _tier_label(tier_code),
            "count": int(row["count"]),
            "last_seen": _dt(row["last_seen"]),
        })
    return rows


async def _recent_events(session: Any, qf: QueryFilter, limit: int = 40) -> list[dict[str, Any]]:
    stmt = (
        qf.apply_user(
            select(
                AnalyticsEvent.created_at,
                AnalyticsEvent.telegram_id,
                AnalyticsEvent.module,
                AnalyticsEvent.action,
                AnalyticsEvent.event_name,
                AnalyticsEvent.event_data,
                AnalyticsEvent.language,
            )
        )
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [
        {
            "created_at": _dt(row["created_at"]),
            "telegram_id": row["telegram_id"],
            "language": row["language"] or "unknown",
            "event_name": _action_label(
                row["module"],
                row["action"],
                row["event_name"],
                row["event_data"],
            ),
            "event_code": row["event_name"],
            "outcome": _event_outcome(row["event_data"]),
        }
        for row in result.mappings()
    ]


async def _tier_distribution(session: Any, qf: QueryFilter) -> dict[str, Any]:
    """Per-tier distribution: number of users + per-tier event count and avg events/user."""
    # Active user list with their event counts
    user_stmt = (
        qf.apply(
            select(
                AnalyticsEvent.telegram_id,
                func.count(AnalyticsEvent.id).label("events"),
            ).where(AnalyticsEvent.telegram_id.is_not(None))
        )
        .group_by(AnalyticsEvent.telegram_id)
    )
    user_rows = list((await session.execute(user_stmt)).mappings())
    telegram_ids = [int(r["telegram_id"]) for r in user_rows]
    tier_map = await _get_user_tiers(session, telegram_ids)

    buckets: dict[str, dict[str, int]] = {tier: {"users": 0, "events": 0} for tier in TIER_DISPLAY_ORDER}
    for r in user_rows:
        tier = tier_map.get(int(r["telegram_id"]), "public")
        if tier not in buckets:
            buckets[tier] = {"users": 0, "events": 0}
        buckets[tier]["users"] += 1
        buckets[tier]["events"] += int(r["events"])

    items: list[dict[str, Any]] = []
    total_users = sum(b["users"] for b in buckets.values()) or 1
    for tier in TIER_DISPLAY_ORDER:
        b = buckets.get(tier, {"users": 0, "events": 0})
        users = b["users"]
        events = b["events"]
        items.append({
            "code": tier,
            "name": _tier_label(tier),
            "users": users,
            "events": events,
            "avg_events_per_user": round(events / users, 2) if users else 0.0,
            "user_percent": round(users * 100 / total_users, 2),
        })
    return {"tiers": items, "total_users": total_users}


async def _hidden_menu_stats(session: Any, qf: QueryFilter) -> list[dict[str, Any]]:
    """Hidden-menu metrics: password trigger count, distinct users, last activation."""
    count = func.count(AnalyticsEvent.id).label("count")
    users = func.count(func.distinct(AnalyticsEvent.telegram_id)).label("users")
    last_at = func.max(AnalyticsEvent.created_at).label("last_at")

    # We extract kind from event_data via JSON field — easier: AnalyticsEvent.action stores the kind too
    # for hidden_access events (see analytics.py).
    stmt = (
        qf.apply(
            select(AnalyticsEvent.action, count, users, last_at).where(
                AnalyticsEvent.module == "hidden_access",
                AnalyticsEvent.event_name == "hidden_access.password_success",
            )
        )
        .group_by(AnalyticsEvent.action)
    )
    result = await session.execute(stmt)
    rows: list[dict[str, Any]] = []
    for row in result.mappings():
        code = str(row["action"] or "unknown")
        rows.append({
            "code": code,
            "name": _hidden_menu_label(code),
            "activations": int(row["count"]),
            "users": int(row["users"] or 0),
            "last_at": _dt(row["last_at"]),
        })
    rows.sort(key=lambda r: r["activations"], reverse=True)
    return rows


# ── HTTP handlers ──────────────────────────────────────────


async def index(_: web.Request) -> web.Response:
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def summary(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    qf = _parse_filter(request)
    async with async_session() as session:
        counts = await _summary_counts(session, qf)
        modules = await _module_heat_window(session, qf)
        languages = await _count_by(session, qf, AnalyticsEvent.language, 8, _language_label)
        actions = await _top_actions(session, qf)
        daily = await _daily_trends(session, qf)
        top_users = await _top_users(session, qf, limit=20)
        recent_events = await _recent_events(session, qf)
        tier_data = await _tier_distribution(session, qf)
        hidden = await _hidden_menu_stats(session, qf)
        annotations = await _annotations_in_range(session, qf.since, qf.until)

    return web.json_response({
        "filter": _filter_dump(qf),
        "summary": counts,
        "modules": modules,
        "actions": actions,
        "daily": daily,
        "languages": languages,
        "top_users": top_users,
        "recent_events": recent_events,
        "tier_distribution": tier_data,
        "hidden_menu": hidden,
        "annotations": [_annotation_dump(a) for a in annotations],
    })


async def heat(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    qf = _parse_filter(request)
    async with async_session() as session:
        rows = await _module_heat(session, qf)
    return web.json_response({"filter": _filter_dump(qf), "modules": rows})


async def trends(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    qf = _parse_filter(request)
    async with async_session() as session:
        rows = await _daily_trends(session, qf)
    return web.json_response({"filter": _filter_dump(qf), "daily": rows})


async def tier_distribution(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    qf = _parse_filter(request)
    async with async_session() as session:
        data = await _tier_distribution(session, qf)
    return web.json_response({"filter": _filter_dump(qf), **data})


async def hidden_menu(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    qf = _parse_filter(request)
    async with async_session() as session:
        rows = await _hidden_menu_stats(session, qf)
    return web.json_response({"filter": _filter_dump(qf), "menus": rows})


# ── Annotations (promo / activity markers) ─────────────────


def _annotation_dump(record: AnalyticsAnnotation) -> dict[str, Any]:
    return {
        "id": record.id,
        "event_date": record.event_date.isoformat() if record.event_date else None,
        "title": record.title,
        "description": record.description or "",
        "color": record.color or "",
        "created_at": _dt(record.created_at),
        "updated_at": _dt(record.updated_at),
    }


async def _annotations_in_range(session: Any, since: datetime, until: datetime) -> list[AnalyticsAnnotation]:
    stmt = (
        select(AnalyticsAnnotation)
        .where(
            AnalyticsAnnotation.event_date >= since.date(),
            AnalyticsAnnotation.event_date < until.date(),
        )
        .order_by(AnalyticsAnnotation.event_date)
    )
    result = await session.execute(stmt)
    return list(result.scalars())


async def annotations_list(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    qf = _parse_filter(request)
    async with async_session() as session:
        records = await _annotations_in_range(session, qf.since, qf.until)
    return web.json_response({
        "filter": _filter_dump(qf),
        "annotations": [_annotation_dump(r) for r in records],
    })


def _validate_annotation_payload(payload: dict[str, Any]) -> tuple[date | None, str, str, str, str | None]:
    """Returns (event_date, title, description, color, error_msg)."""
    raw_date = (payload.get("event_date") or "").strip()
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    color = (payload.get("color") or "").strip()

    if not raw_date:
        return None, "", "", "", "event_date 必填 (YYYY-MM-DD)"
    try:
        event_date = date.fromisoformat(raw_date)
    except ValueError:
        return None, "", "", "", "event_date 格式应为 YYYY-MM-DD"
    if not title:
        return None, "", "", "", "title 必填"
    if len(title) > 100:
        return None, "", "", "", "title 不能超过 100 字符"
    if color and len(color) > 20:
        return None, "", "", "", "color 不能超过 20 字符"

    return event_date, title, description, color, None


async def annotations_create(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)
    try:
        payload = await request.json()
    except Exception:
        return _json_error("invalid JSON body", 400)
    if not isinstance(payload, dict):
        return _json_error("payload must be a JSON object", 400)

    event_date, title, description, color, error_msg = _validate_annotation_payload(payload)
    if error_msg:
        return _json_error(error_msg, 400)

    async with async_session() as session:
        record = AnalyticsAnnotation(
            event_date=event_date,
            title=title,
            description=description or None,
            color=color or None,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
    return web.json_response(_annotation_dump(record), status=201)


async def annotations_update(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)
    try:
        record_id = int(request.match_info.get("id", "0"))
    except ValueError:
        return _json_error("invalid id", 400)
    try:
        payload = await request.json()
    except Exception:
        return _json_error("invalid JSON body", 400)
    if not isinstance(payload, dict):
        return _json_error("payload must be a JSON object", 400)

    event_date, title, description, color, error_msg = _validate_annotation_payload(payload)
    if error_msg:
        return _json_error(error_msg, 400)

    async with async_session() as session:
        record = await session.get(AnalyticsAnnotation, record_id)
        if not record:
            return _json_error("annotation not found", 404)
        record.event_date = event_date
        record.title = title
        record.description = description or None
        record.color = color or None
        await session.commit()
        await session.refresh(record)
    return web.json_response(_annotation_dump(record))


async def annotations_delete(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)
    try:
        record_id = int(request.match_info.get("id", "0"))
    except ValueError:
        return _json_error("invalid id", 400)

    async with async_session() as session:
        record = await session.get(AnalyticsAnnotation, record_id)
        if not record:
            return _json_error("annotation not found", 404)
        await session.delete(record)
        await session.commit()
    return web.json_response({"deleted": record_id})


# ── Excel export ───────────────────────────────────────────


def _xlsx_response(headers: list[str], rows: list[list[Any]], filename: str) -> web.Response:
    try:
        from openpyxl import Workbook
    except ImportError:
        return _json_error("openpyxl 未安装，请在容器内 pip install openpyxl", 500)

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    # Auto width (rough heuristic)
    for col_idx, header in enumerate(headers, start=1):
        max_len = len(str(header))
        for row in rows:
            if col_idx - 1 < len(row):
                cell_val = str(row[col_idx - 1] or "")
                if len(cell_val) > max_len:
                    max_len = len(cell_val)
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 60)

    buf = io.BytesIO()
    wb.save(buf)
    return web.Response(
        body=buf.getvalue(),
        headers={
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


async def export(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    export_type = (request.query.get("type") or "").strip().lower()
    qf = _parse_filter(request)
    suffix = qf.period_label
    today = date.today().isoformat()

    async with async_session() as session:
        if export_type == "actions":
            rows = await _top_actions(session, qf, limit=200)
            return _xlsx_response(
                ["排名", "动作", "代码", "次数", "去重用户数", "占比%"],
                [[i + 1, r["name"], r["code"], r["count"], r["users"], r["percent"]] for i, r in enumerate(rows)],
                f"功能动作排行_{suffix}_{today}.xlsx",
            )
        if export_type == "users":
            rows = await _top_users(session, qf, limit=500)
            return _xlsx_response(
                ["排名", "TGID", "用户名", "等级", "语言", "事件数", "最后访问"],
                [
                    [i + 1, r["telegram_id"], r["display_name"], r["tier_label"], _language_label(r["language"]), r["count"], r["last_seen"] or ""]
                    for i, r in enumerate(rows)
                ],
                f"用户排行_{suffix}_{today}.xlsx",
            )
        if export_type == "events":
            rows = await _recent_events(session, qf, limit=2000)
            return _xlsx_response(
                ["时间", "TGID", "语言", "事件", "代码", "结果"],
                [
                    [r["created_at"] or "", r["telegram_id"], _language_label(r["language"]), r["event_name"], r["event_code"], r["outcome"] or ""]
                    for r in rows
                ],
                f"事件明细_{suffix}_{today}.xlsx",
            )
        if export_type == "trends":
            rows = await _daily_trends(session, qf)
            return _xlsx_response(
                ["日期", "事件总数", "活跃用户", "新增用户", "按钮点击", "价格查询"],
                [
                    [r["day"], r["events"], r["active_users"], r["new_users"], r["callbacks"], r["price_queries"]]
                    for r in rows
                ],
                f"每日趋势_{suffix}_{today}.xlsx",
            )
        if export_type == "hidden_menu":
            rows = await _hidden_menu_stats(session, qf)
            return _xlsx_response(
                ["隐藏菜单", "代码", "激活次数", "去重用户", "最后激活"],
                [[r["name"], r["code"], r["activations"], r["users"], r["last_at"] or ""] for r in rows],
                f"隐藏菜单数据_{suffix}_{today}.xlsx",
            )

    return _json_error(f"unknown export type: {export_type}", 400)


# ── Misc ──────────────────────────────────────────────────


def _filter_dump(qf: QueryFilter) -> dict[str, Any]:
    return {
        "since": qf.since.isoformat(),
        "until": qf.until.isoformat(),
        "period": qf.period_label,
        "exclude_test_count": len(qf.exclude_test_ids),
    }


# ── HTML template (rewritten with ECharts) ─────────────────


DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>A-BF Bot 用户埋点 Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #182032;
      --muted: #657085;
      --line: #d9deea;
      --accent: #1264a3;
      --accent-2: #11845b;
      --warn: #a35c12;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      background: #101827;
      color: #fff;
      padding: 18px 24px;
      border-bottom: 1px solid #0b1220;
    }
    header h1 { margin: 0 0 4px; font-size: 20px; font-weight: 700; }
    header p { margin: 0; color: #b9c2d3; }
    main { max-width: 1400px; margin: 0 auto; padding: 20px; }

    .toolbar {
      display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
      margin-bottom: 16px; padding: 12px; background: var(--panel);
      border: 1px solid var(--line); border-radius: 8px;
    }
    .toolbar label { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); }
    select, input, button {
      height: 34px; border: 1px solid var(--line); border-radius: 6px;
      background: #fff; padding: 0 10px; color: var(--text);
    }
    input[type=date] { min-width: 140px; }
    input[type=password] { min-width: 200px; }
    button {
      background: var(--accent); color: #fff; border-color: var(--accent);
      cursor: pointer; font-weight: 600;
    }
    button.ghost { background: #fff; color: var(--accent); }
    .toggle {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 0 10px; height: 34px; border: 1px solid var(--line);
      border-radius: 6px; background: #fff; cursor: pointer; user-select: none;
    }
    .toggle input { transform: translateY(1px); }
    .status { color: var(--muted); margin-left: auto; }
    .status.error { color: var(--danger); font-weight: 600; }

    .grid { display: grid; gap: 14px; }
    .cards { grid-template-columns: repeat(5, minmax(150px, 1fr)); }
    .two { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 14px; }
    .three { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 14px; }

    .panel {
      background: var(--panel); border: 1px solid var(--line);
      border-radius: 8px; padding: 14px;
      box-shadow: 0 1px 2px rgba(16, 24, 39, 0.04);
    }
    .panel h2 {
      margin: 0 0 10px; font-size: 15px; display: flex;
      align-items: center; justify-content: space-between; gap: 8px;
    }
    .chart-tools { display: inline-flex; gap: 4px; }
    .chart-tools button {
      height: 26px; padding: 0 8px; font-size: 12px;
      background: #fff; color: var(--accent); border-color: var(--line);
      font-weight: 500;
    }
    .chart-tools button.active {
      background: var(--accent); color: #fff; border-color: var(--accent);
    }
    .chart { width: 100%; height: 280px; }
    .chart.tall { height: 340px; }

    .card .label { color: var(--muted); font-size: 13px; }
    .card .value { font-size: 26px; font-weight: 750; margin-top: 4px; }
    .card .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }

    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
    th { color: var(--muted); font-size: 12px; font-weight: 650; }
    td { font-variant-numeric: tabular-nums; }
    .empty { color: var(--muted); padding: 18px 0; text-align: center; }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 12px; font-weight: 600;
    }
    .badge.t-public { background: #eef2f7; color: #506178; }
    .badge.t-vip_inventory { background: #e1efff; color: #11538f; }
    .badge.t-svip_inventory { background: #f1e5ff; color: #6a1aab; }
    .badge.t-vvip_inventory { background: #fff1d6; color: #8d5400; }
    .badge.t-vandych { background: #d9f6e8; color: #1a6b41; }
    .badge.t-service_admin { background: #fde0e0; color: #993131; }
    .delta-pos { color: var(--accent-2); font-weight: 600; }
    .delta-neg { color: var(--danger); font-weight: 600; }

    .export-bar {
      display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px;
    }
    .export-bar button {
      height: 28px; padding: 0 10px; font-size: 12px;
      background: #fff; color: var(--accent-2); border-color: var(--accent-2);
      font-weight: 600;
    }

    @media (max-width: 1100px) {
      .cards { grid-template-columns: repeat(2, 1fr); }
      .two, .three { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>A-BF Telegram Bot 用户埋点</h1>
    <p>客户使用路径、模块热度、每日趋势、用户活跃度与隐藏菜单数据。</p>
  </header>
  <main>
    <div class="toolbar">
      <label>周期
        <select id="period">
          <option value="day">今天</option>
          <option value="week" selected>近 7 天</option>
          <option value="month">近 30 天</option>
          <option value="custom">自定义</option>
        </select>
      </label>
      <label class="custom-range" style="display:none">
        起 <input id="startDate" type="date" />
      </label>
      <label class="custom-range" style="display:none">
        止 <input id="endDate" type="date" />
      </label>
      <label class="toggle"><input id="includeTest" type="checkbox" /> 包含测试号</label>
      <input id="token" type="password" placeholder="访问 Token（如已配置）" />
      <button id="refresh">刷新</button>
      <span id="status" class="status">等待加载</span>
    </div>

    <section class="grid cards">
      <div class="panel card"><div class="label">总事件</div><div id="totalEvents" class="value">-</div><div class="sub">消息 + 按钮点击</div></div>
      <div class="panel card"><div class="label">活跃用户</div><div id="activeUsers" class="value">-</div><div class="sub">去重 Telegram 用户</div></div>
      <div class="panel card"><div class="label">按钮点击</div><div id="callbacks" class="value">-</div><div class="sub">菜单路径行为</div></div>
      <div class="panel card"><div class="label">文本输入</div><div id="messages" class="value">-</div><div class="sub">不保存原文</div></div>
      <div class="panel card"><div class="label">15 分钟活跃</div><div id="recentUsers" class="value">-</div><div class="sub">实时访问热度</div></div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>每日趋势
          <span class="chart-tools" data-chart="trends">
            <button data-type="line" class="active">折线</button>
            <button data-type="bar">柱状</button>
          </span>
        </h2>
        <div id="trendsChart" class="chart tall"></div>
      </div>
      <div class="panel">
        <h2>语言分布
          <span class="chart-tools" data-chart="languages">
            <button data-type="pie" class="active">饼图</button>
            <button data-type="bar">柱状</button>
          </span>
        </h2>
        <div id="languagesChart" class="chart tall"></div>
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>模块热度（含周期对比）
          <span class="chart-tools" data-chart="heat">
            <button data-type="bar" class="active">柱状</button>
            <button data-type="pie">饼图</button>
          </span>
        </h2>
        <div id="heatChart" class="chart"></div>
      </div>
      <div class="panel">
        <h2>会员等级分布
          <span class="chart-tools" data-chart="tiers">
            <button data-type="pie" class="active">饼图</button>
            <button data-type="bar">柱状</button>
          </span>
        </h2>
        <div id="tiersChart" class="chart"></div>
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>功能动作排行
          <span class="chart-tools">
            <button class="active export-link" data-export="actions">导出 Excel</button>
          </span>
        </h2>
        <div id="actionsChart" class="chart tall"></div>
      </div>
      <div class="panel">
        <h2>隐藏菜单激活
          <span class="chart-tools">
            <button class="active export-link" data-export="hidden_menu">导出 Excel</button>
          </span>
        </h2>
        <div id="hiddenChart" class="chart tall"></div>
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>用户排行
          <span class="chart-tools">
            <button class="active export-link" data-export="users">导出 Excel</button>
          </span>
        </h2>
        <table>
          <thead><tr><th>用户</th><th>TGID</th><th>等级</th><th>语言</th><th>事件</th><th>最后访问</th></tr></thead>
          <tbody id="topUsers"></tbody>
        </table>
      </div>
      <div class="panel">
        <h2>最近事件
          <span class="chart-tools">
            <button class="active export-link" data-export="events">导出 Excel</button>
          </span>
        </h2>
        <table>
          <thead><tr><th>时间</th><th>TGID</th><th>事件</th><th>结果</th></tr></thead>
          <tbody id="recentEvents"></tbody>
        </table>
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>活动 / 大促节点标注
          <span class="chart-tools">
            <button id="addAnnotationBtn">+ 新建标注</button>
          </span>
        </h2>
        <p style="color:var(--muted);margin:0 0 10px;font-size:13px">
          标注会以虚线形式叠加到上方"每日趋势"图，方便对照流量变化。
        </p>
        <form id="annotationForm" style="display:none;margin-bottom:10px;padding:10px;border:1px dashed var(--line);border-radius:6px;">
          <input type="hidden" id="annotationId" />
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <input id="annotationDate" type="date" required style="min-width:140px" />
            <input id="annotationTitle" type="text" required placeholder="标题（如：双 11 促销）" maxlength="100" style="min-width:200px;flex:1" />
            <input id="annotationColor" type="color" value="#a35c12" title="颜色" style="min-width:40px;width:56px;padding:0" />
          </div>
          <textarea id="annotationDesc" placeholder="备注（可选）" rows="2" style="margin-top:8px;width:100%;padding:6px 10px;border:1px solid var(--line);border-radius:6px;font-family:inherit;font-size:13px;"></textarea>
          <div style="margin-top:8px;display:flex;gap:6px;">
            <button type="submit" id="annotationSubmit">保存</button>
            <button type="button" id="annotationCancel" class="ghost">取消</button>
          </div>
        </form>
        <table>
          <thead><tr><th>日期</th><th>标题</th><th>备注</th><th>颜色</th><th style="width:120px">操作</th></tr></thead>
          <tbody id="annotationsTable"></tbody>
        </table>
      </div>
    </section>
  </main>

  <script>
    const $ = (id) => document.getElementById(id);
    const fmt = new Intl.NumberFormat('zh-CN');

    const charts = {};      // id → echarts instance
    const chartTypes = {    // chart -> current type
      trends: 'line', languages: 'pie', heat: 'bar', tiers: 'pie',
      actions: 'bar', hidden: 'bar',
    };
    let lastData = null;

    function getChart(id) {
      if (!charts[id]) charts[id] = echarts.init($(id));
      return charts[id];
    }

    function setText(id, value) {
      $(id).textContent = Number.isFinite(value) ? fmt.format(value) : '-';
    }
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (c) => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
      }[c]));
    }
    function shortTime(value) {
      if (!value) return '-';
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return value;
      return d.toLocaleString('zh-CN', { hour12: false });
    }
    function deltaText(delta, deltaPct) {
      if (!delta) return '<span style="color:#9aa3b5">→ 0</span>';
      const cls = delta > 0 ? 'delta-pos' : 'delta-neg';
      const arrow = delta > 0 ? '↑' : '↓';
      return `<span class="${cls}">${arrow} ${fmt.format(Math.abs(delta))} (${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(1)}%)</span>`;
    }

    function trendsOption(daily, type, annotations) {
      const days = daily.map(r => r.day.slice(5));
      const dayKeys = daily.map(r => r.day);
      const series = [
        { name: '新增用户', data: daily.map(r => r.new_users), color: '#1264a3' },
        { name: '活跃用户', data: daily.map(r => r.active_users), color: '#11845b' },
        { name: '按钮点击', data: daily.map(r => r.callbacks), color: '#a35c12' },
        { name: '价格查询', data: daily.map(r => r.price_queries), color: '#b42318' },
      ];

      // 把活动节点转换成 markLine 数据，xAxis 是 category 类型，所以用 xAxis index
      const annotationLines = (annotations || []).filter(a => dayKeys.includes(a.event_date)).map(a => ({
        xAxis: a.event_date.slice(5),
        label: {
          formatter: a.title,
          fontSize: 11,
          color: a.color || '#a35c12',
          fontWeight: 600,
          backgroundColor: 'rgba(255,255,255,0.85)',
          padding: [2, 4],
          borderRadius: 3,
          position: 'insideEndTop',
        },
        lineStyle: {
          color: a.color || '#a35c12',
          type: 'dashed',
          width: 1.5,
        },
      }));

      const seriesItems = series.map((s, idx) => {
        const item = {
          name: s.name, type: type, data: s.data,
          smooth: type === 'line', itemStyle: { color: s.color },
          lineStyle: type === 'line' ? { width: 2 } : undefined,
        };
        // 只把 markLine 挂在第一条线上，避免多条线重复绘制
        if (idx === 0 && annotationLines.length) {
          item.markLine = { silent: true, symbol: 'none', data: annotationLines };
        }
        return item;
      });

      return {
        tooltip: { trigger: 'axis' },
        legend: { bottom: 0, textStyle: { fontSize: 12 } },
        grid: { left: 40, right: 20, top: 30, bottom: 40 },
        xAxis: { type: 'category', data: days, axisLabel: { fontSize: 11 } },
        yAxis: { type: 'value', axisLabel: { fontSize: 11 } },
        series: seriesItems,
      };
    }

    function pieOrBarOption(rows, type, valueKey='count') {
      if (!rows || !rows.length) {
        return { title: { text: '暂无数据', left: 'center', top: 'center', textStyle: { fontSize: 13, color: '#9aa3b5' } } };
      }
      if (type === 'pie') {
        return {
          tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
          legend: { bottom: 0, textStyle: { fontSize: 11 } },
          series: [{
            type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: true,
            label: { show: true, formatter: '{b}\n{d}%', fontSize: 11 },
            data: rows.map(r => ({ name: r.name, value: r[valueKey] })),
          }],
        };
      }
      return {
        tooltip: { trigger: 'axis' },
        grid: { left: 110, right: 30, top: 10, bottom: 20 },
        xAxis: { type: 'value', axisLabel: { fontSize: 11 } },
        yAxis: { type: 'category', data: rows.map(r => r.name).reverse(), axisLabel: { fontSize: 11 } },
        series: [{
          type: 'bar',
          data: rows.map(r => r[valueKey]).reverse(),
          itemStyle: { color: '#1264a3' },
          label: { show: true, position: 'right', fontSize: 11 },
        }],
      };
    }

    function heatOption(rows, type) {
      if (!rows || !rows.length) return pieOrBarOption(rows, type);
      if (type === 'pie') return pieOrBarOption(rows, 'pie');
      return {
        tooltip: { trigger: 'axis', formatter: (params) => {
          const row = rows[params[0].dataIndex];
          return `${row.name}<br/>本期：${fmt.format(row.count)} 次（${row.users} 人）<br/>上期：${fmt.format(row.previous_count)} 次<br/>变化：${row.delta >= 0 ? '+' : ''}${row.delta_percent}%`;
        } },
        legend: { bottom: 0, textStyle: { fontSize: 11 } },
        grid: { left: 100, right: 30, top: 10, bottom: 40 },
        xAxis: { type: 'value', axisLabel: { fontSize: 11 } },
        yAxis: { type: 'category', data: rows.map(r => r.name).reverse(), axisLabel: { fontSize: 11 } },
        series: [
          {
            name: '本期', type: 'bar',
            data: rows.map(r => r.count).reverse(),
            itemStyle: { color: '#1264a3' },
            label: { show: true, position: 'right', fontSize: 11 },
          },
          {
            name: '上期', type: 'bar',
            data: rows.map(r => r.previous_count).reverse(),
            itemStyle: { color: '#9fbcd8' },
          },
        ],
      };
    }

    function tiersOption(tiers, type) {
      const filtered = tiers.filter(t => t.users > 0);
      if (!filtered.length) return pieOrBarOption([], type);
      if (type === 'pie') return pieOrBarOption(filtered.map(t => ({ name: t.name, count: t.users })), 'pie', 'count');
      return {
        tooltip: { trigger: 'axis', formatter: (params) => {
          const t = filtered[params[0].dataIndex];
          return `${t.name}<br/>用户数：${t.users}<br/>事件总数：${t.events}<br/>均事件/人：${t.avg_events_per_user}`;
        } },
        grid: { left: 80, right: 30, top: 10, bottom: 20 },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: filtered.map(t => t.name).reverse() },
        series: [{
          type: 'bar',
          data: filtered.map(t => t.users).reverse(),
          itemStyle: { color: '#11845b' },
          label: { show: true, position: 'right', fontSize: 11 },
        }],
      };
    }

    function applyChart(id, optionFn) {
      const chart = getChart(id);
      const opt = optionFn();
      if (opt) chart.setOption(opt, true);
    }

    function renderAll(data) {
      lastData = data;

      setText('totalEvents', data.summary.total_events);
      setText('activeUsers', data.summary.active_users);
      setText('callbacks', data.summary.callbacks);
      setText('messages', data.summary.messages);
      setText('recentUsers', data.summary.recent_active_users);

      applyChart('trendsChart', () => trendsOption(data.daily, chartTypes.trends, data.annotations));
      applyChart('languagesChart', () => pieOrBarOption(data.languages, chartTypes.languages));
      applyChart('heatChart', () => heatOption(data.modules, chartTypes.heat));
      applyChart('tiersChart', () => tiersOption(data.tier_distribution.tiers, chartTypes.tiers));
      applyChart('actionsChart', () => pieOrBarOption(data.actions, chartTypes.actions));
      applyChart('hiddenChart', () => pieOrBarOption(data.hidden_menu.map(h => ({
        name: h.name, count: h.activations,
      })), chartTypes.hidden));

      // Top users table with tier badges
      $('topUsers').innerHTML = (data.top_users || []).map(u => `<tr>
        <td>${escapeHtml(u.display_name)}</td>
        <td>${escapeHtml(u.telegram_id)}</td>
        <td><span class="badge t-${u.tier_code}">${escapeHtml(u.tier_label)}</span></td>
        <td>${escapeHtml(u.language)}</td>
        <td>${fmt.format(u.count)}</td>
        <td>${shortTime(u.last_seen)}</td>
      </tr>`).join('') || '<tr><td colspan="6" class="empty">暂无数据</td></tr>';

      $('recentEvents').innerHTML = (data.recent_events || []).map(e => `<tr>
        <td>${shortTime(e.created_at)}</td>
        <td>${escapeHtml(e.telegram_id)}</td>
        <td>${escapeHtml(e.event_name)}</td>
        <td>${escapeHtml(e.outcome || '-')}</td>
      </tr>`).join('') || '<tr><td colspan="4" class="empty">暂无数据</td></tr>';

      renderAnnotations(data.annotations || []);
    }

    // ── Annotations management ──────────────────────────────
    function renderAnnotations(items) {
      if (!items.length) {
        $('annotationsTable').innerHTML = '<tr><td colspan="5" class="empty">暂无标注，点右上"新建标注"添加</td></tr>';
        return;
      }
      $('annotationsTable').innerHTML = items.map(a => `<tr data-id="${a.id}">
        <td>${escapeHtml(a.event_date)}</td>
        <td><strong>${escapeHtml(a.title)}</strong></td>
        <td style="color:var(--muted)">${escapeHtml(a.description || '-')}</td>
        <td><span style="display:inline-block;width:18px;height:14px;border-radius:3px;background:${escapeHtml(a.color || '#a35c12')};border:1px solid var(--line)"></span> <span style="color:var(--muted);font-size:12px">${escapeHtml(a.color || '默认')}</span></td>
        <td>
          <button class="ghost annot-edit" data-id="${a.id}" style="height:26px;padding:0 8px;font-size:12px">编辑</button>
          <button class="annot-del" data-id="${a.id}" style="height:26px;padding:0 8px;font-size:12px;background:#b42318;border-color:#b42318">删除</button>
        </td>
      </tr>`).join('');
    }

    function showAnnotationForm(record) {
      $('annotationForm').style.display = '';
      $('annotationId').value = record ? record.id : '';
      $('annotationDate').value = record ? record.event_date : new Date().toISOString().slice(0, 10);
      $('annotationTitle').value = record ? record.title : '';
      $('annotationDesc').value = record ? (record.description || '') : '';
      $('annotationColor').value = (record && record.color) || '#a35c12';
      $('annotationTitle').focus();
    }
    function hideAnnotationForm() {
      $('annotationForm').style.display = 'none';
      $('annotationForm').reset();
      $('annotationId').value = '';
    }

    async function annotationApi(method, path, body) {
      const token = $('token').value.trim();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['X-Analytics-Token'] = token;
      const res = await fetch(path, {
        method, headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        let msg = '请求失败：' + res.status;
        try {
          const data = await res.json();
          if (data.error) msg = data.error;
        } catch (_) {}
        throw new Error(msg);
      }
      return res.status === 204 ? null : res.json();
    }

    document.addEventListener('click', async (e) => {
      const editBtn = e.target.closest('.annot-edit');
      if (editBtn) {
        const id = Number(editBtn.dataset.id);
        const record = (lastData?.annotations || []).find(a => a.id === id);
        if (record) showAnnotationForm(record);
        return;
      }
      const delBtn = e.target.closest('.annot-del');
      if (delBtn) {
        if (!confirm('确认删除这个标注吗？')) return;
        const id = Number(delBtn.dataset.id);
        try {
          await annotationApi('DELETE', `/api/annotations/${id}`);
          await load();
        } catch (err) {
          alert(err.message);
        }
        return;
      }
    });

    $('addAnnotationBtn').addEventListener('click', () => showAnnotationForm(null));
    $('annotationCancel').addEventListener('click', hideAnnotationForm);
    $('annotationForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = $('annotationId').value;
      const payload = {
        event_date: $('annotationDate').value,
        title: $('annotationTitle').value.trim(),
        description: $('annotationDesc').value.trim(),
        color: $('annotationColor').value,
      };
      try {
        if (id) {
          await annotationApi('PUT', `/api/annotations/${id}`, payload);
        } else {
          await annotationApi('POST', '/api/annotations', payload);
        }
        hideAnnotationForm();
        await load();
      } catch (err) {
        alert(err.message);
      }
    });

    function buildQuery(extra = {}) {
      const params = new URLSearchParams();
      const period = $('period').value;
      params.set('period', period);
      if (period === 'custom') {
        if ($('startDate').value) params.set('start_date', $('startDate').value);
        if ($('endDate').value) params.set('end_date', $('endDate').value);
      }
      params.set('include_test', $('includeTest').checked ? '1' : '0');
      const token = $('token').value.trim();
      if (token) params.set('token', token);
      for (const [k, v] of Object.entries(extra)) params.set(k, v);
      return params;
    }

    async function load() {
      $('status').textContent = '加载中...';
      $('status').className = 'status';
      const params = buildQuery();
      localStorage.setItem('analyticsToken', $('token').value.trim());

      const headers = $('token').value.trim() ? { 'X-Analytics-Token': $('token').value.trim() } : {};
      const res = await fetch('/api/summary?' + params.toString(), { headers });
      if (res.status === 401) {
        $('status').textContent = 'Token 不正确或未填写';
        $('status').className = 'status error';
        return;
      }
      if (!res.ok) {
        $('status').textContent = '加载失败：' + res.status;
        $('status').className = 'status error';
        return;
      }
      const data = await res.json();
      renderAll(data);
      $('status').textContent = `已更新：${shortTime(new Date().toISOString())}（共 ${fmt.format(data.summary.total_events)} 事件）`;
    }

    function exportXlsx(type) {
      const params = buildQuery({ type });
      window.open('/api/export?' + params.toString(), '_blank');
    }

    // Chart-type switching
    document.addEventListener('click', (e) => {
      const tools = e.target.closest('.chart-tools');
      if (tools && e.target.tagName === 'BUTTON') {
        // Export button
        const exportType = e.target.dataset.export;
        if (exportType) {
          exportXlsx(exportType);
          return;
        }
        // Chart-type switch
        const chartName = tools.dataset.chart;
        const newType = e.target.dataset.type;
        if (!chartName || !newType) return;
        chartTypes[chartName] = newType;
        for (const btn of tools.querySelectorAll('button')) btn.classList.toggle('active', btn === e.target);
        if (lastData) renderAll(lastData);
      }
    });

    // Custom date toggling
    function syncCustomRange() {
      const showing = $('period').value === 'custom';
      for (const el of document.querySelectorAll('.custom-range')) el.style.display = showing ? '' : 'none';
    }
    $('period').addEventListener('change', () => { syncCustomRange(); load(); });
    $('includeTest').addEventListener('change', () => load());
    $('refresh').addEventListener('click', () => load().catch(err => {
      $('status').textContent = '加载失败：' + err.message;
      $('status').className = 'status error';
    }));

    window.addEventListener('resize', () => {
      for (const c of Object.values(charts)) c.resize();
    });

    // Init
    $('token').value = localStorage.getItem('analyticsToken') || '';
    syncCustomRange();
    // Default custom range = last 7d
    const today = new Date();
    const weekAgo = new Date(today.getTime() - 6 * 86400000);
    $('endDate').value = today.toISOString().slice(0, 10);
    $('startDate').value = weekAgo.toISOString().slice(0, 10);
    load();
  </script>
</body>
</html>
"""


# ── App factory + main ─────────────────────────────────────


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/summary", summary)
    app.router.add_get("/api/heat", heat)
    app.router.add_get("/api/trends", trends)
    app.router.add_get("/api/tier-distribution", tier_distribution)
    app.router.add_get("/api/hidden-menu", hidden_menu)
    app.router.add_get("/api/export", export)
    app.router.add_get("/api/annotations", annotations_list)
    app.router.add_post("/api/annotations", annotations_create)
    app.router.add_put(r"/api/annotations/{id:\d+}", annotations_update)
    app.router.add_delete(r"/api/annotations/{id:\d+}", annotations_delete)
    return app


async def main_async() -> None:
    setup_logging(settings.log_level, settings.log_format)
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=settings.analytics_dashboard_host,
        port=settings.analytics_dashboard_port,
    )
    await site.start()
    logger.info(
        "Analytics dashboard started at http://%s:%s",
        settings.analytics_dashboard_host,
        settings.analytics_dashboard_port,
    )
    await asyncio.Event().wait()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
