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
from bot.models.user import User
from bot.services.discount_sheet import find_discount_by_sku, fuzzy_find, get_discounts
from bot.services.outdoor_prices import get_outdoor_price_brand_titles, get_outdoor_price_items
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



async def tool_create_ae_promo_code(
    store_name: str,
    discount_value: float,
    min_order_amount: float,
    validity_days: int,
    total_num: int,
    num_per_buyer: int,
    campaign_name: str = "WeCom Auto Promo",
    promo_code: str = None
) -> str:
    """为速卖通指定店铺创建折扣码 (Promo Code)。
    
    Args:
        store_name: 店铺名称 (必须是中文，建议如 "主店", "配件店" 等，作为提取cookie的key)
        discount_value: 折扣减免的金额 (固定减多少美元)
        min_order_amount: 需要满多少美元才减 (满减门槛)
        validity_days: 有效期天数
        total_num: 发行的代码总数
        num_per_buyer: 每人限购数量
        campaign_name: 在后台显示的活动名称
        promo_code: 若为空，将自动生成 12 位专属码
    """
    import random
    import string
    import time
    from bot.services.aliexpress_mtop import MTOPClient
    
    if not promo_code:
        promo_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        
    client = MTOPClient(store_name)
    
    now_ms = int(time.time() * 1000)
    end_ms = now_ms + (validity_days * 24 * 60 * 60 * 1000)
    
    api = "mtop.global.merchant.promotion.ae.voucher.save"
    data = {
        "channelId": "238299", "codeScope": "public", "promotionName": campaign_name,
        "autoRenew": True, "canApplyBefore": False, "hasUseCondition": "1",
        "denominationNew": discount_value, "releasedNum": total_num, "numPerBuyer": num_per_buyer,
        "countryScope": "all_country", "productScope": "entire_shop",
        "couponCode": promo_code, "minOrderAmountNew": min_order_amount,
        "couponChannelType": "0", "consumeStartTime": now_ms, "consumeEndTime": end_ms,
        "applyStartTime": None, "memberLevel": "A0", "displayChannel": "[]",
        "shipToCountryCodes": "", "fromAgent": False, "updateAutoRenewFlag": True
    }
    
    try:
        res = await client.request(api, data)
        ret_msg = str(res.get("ret", [""])[0])
        if "SUCCESS" in ret_msg:
            return f"✅ 成功在【{store_name}】发码！\n\n🏷️ 折扣代码: `{promo_code}`\n💰 规则: 满 ${min_order_amount} 减 ${discount_value}\n🎟️ 发放数量: {total_num} 张 (每人限用 {num_per_buyer} 张)\n⏳ 有效期: 约 {validity_days} 天"
        else:
            return f"⚠️ 在【{store_name}】发码失败：{res.get('ret')}"
    except ValueError as e:
        if str(e) == "SESSION_EXPIRED":
            return f"❌ {store_name} 的授权已彻底失效，未能创建折扣码。\n\n请老板在浏览器重新登录该店铺抓取 Cookie 后，发送以下格式重新绑定授权：\n`/update_cookie {store_name} 你的新Cookie`"
        return f"❌ 发码内部发生错误：{e}"
    except Exception as e:
        return f"❌ 发码发生异常错误：{e}"


_PRICE_LABELS: dict[str, str] = {
    "rub": "卢布",
    "cny": "人民币",
    "cny_ru": "人民币(俄货)",
    "cny_cn": "人民币(国内)",
    "usd": "美元",
}


async def tool_query_price(sku: str, tier: str = "svip", brand: str = "") -> str:
    """查询指定 SKU 的价格（RUB/CNY）。

    tier: vip=仅卢布 / svip=卢布+人民币（默认）/ vvip=美元+卢布+人民币
    brand: 品牌名可选（填写可加快搜索速度）
    """
    tier_norm = (tier or "svip").lower()
    if tier_norm not in {"vip", "svip", "vvip"}:
        tier_norm = "svip"
    sku_q = (sku or "").strip()
    if not sku_q:
        return "❌ 请提供 SKU 型号。"

    try:
        all_titles = await get_outdoor_price_brand_titles()
    except Exception as exc:
        logger.exception("get_outdoor_price_brand_titles failed")
        return f"❌ 获取品牌列表失败：{exc}"

    # 如果指定了品牌，只搜该品牌
    brand_q = (brand or "").strip().casefold()
    search_titles = (
        [t for t in all_titles if brand_q in t.casefold()] or all_titles
        if brand_q else all_titles
    )

    import re
    sku_pattern = re.sub(r"\s+", "", sku_q).casefold()
    found: list[tuple[str, str, dict[str, str]]] = []  # (brand, sku, prices)

    for title in search_titles:
        try:
            items, _ = await get_outdoor_price_items(title, tier_norm)
        except Exception:
            continue
        for item in items:
            item_key = re.sub(r"\s+", "", item.sku).casefold()
            if sku_pattern in item_key or item_key in sku_pattern:
                found.append((title, item.sku, item.prices or {}))
        if found and brand_q:
            break  # 指定品牌时找到即停

    if not found:
        return f"❌ 未找到 {sku_q} 的价格数据（已查 {len(search_titles)} 个品牌 tab）。"

    lines: list[str] = [f"💰 价格查询（{tier_norm.upper()} 档）\n"]
    for brand_title, sku_val, prices in found[:5]:
        lines.append(f"【{brand_title}】{sku_val}")
        if prices:
            for key, val in prices.items():
                label = _PRICE_LABELS.get(key, key)
                lines.append(f"  {label}：{val}")
        else:
            lines.append("  暂无价格数据")
        lines.append("")
    if len(found) > 5:
        lines.append(f"…共 {len(found)} 条，已显示前 5 条")
    return "\n".join(lines).rstrip()


async def tool_get_discount(sku: str = "") -> str:
    """查询 Vandych VIP 折扣信息。不传 sku 则列出所有有效折扣。"""
    try:
        items = await get_discounts()
    except Exception as exc:
        logger.exception("tool_get_discount failed")
        return f"❌ 获取折扣数据失败：{exc}"

    if not items:
        return "📭 当前没有有效的折扣数据。"

    q = (sku or "").strip()
    if q:
        matches = fuzzy_find(items, q)
        if not matches:
            return f"❌ 未找到 {q} 的折扣信息。"
        target_items = [item for _, item in matches[:5]]
    else:
        target_items = items[:20]

    lines = ["🏷️ 折扣信息\n"]
    for item in target_items:
        lines.append(f"**{item.model}**")
        if item.discount:
            lines.append(f"  折扣：{item.discount}")
        if item.code and item.code.casefold() not in ("discount", ""):
            lines.append(f"  折扣码：{item.code}")
        if item.link and item.link.casefold() not in ("links", "link", ""):
            lines.append(f"  链接：{item.link}")
        if item.notes:
            lines.append(f"  备注：{item.notes}")
        lines.append("")
    if not q and len(items) > 20:
        lines.append(f"…共 {len(items)} 条，已显示前 20 条")
    return "\n".join(lines).rstrip()


async def tool_get_user_ranking(period_days: int = 1, top_n: int = 10) -> str:
    """查询 Telegram Bot 活跃用户排行（按事件数排序）。"""
    today = date.today()
    since = datetime.combine(today - timedelta(days=period_days - 1), time.min)
    until = datetime.combine(today + timedelta(days=1), time.min)
    label = "今天" if period_days == 1 else f"近 {period_days} 天"

    try:
        async with async_session() as session:
            rows = (await session.execute(
                select(
                    AnalyticsEvent.telegram_id,
                    func.count(AnalyticsEvent.id).label("cnt"),
                )
                .where(
                    AnalyticsEvent.created_at >= since,
                    AnalyticsEvent.created_at < until,
                    AnalyticsEvent.telegram_id.is_not(None),
                )
                .group_by(AnalyticsEvent.telegram_id)
                .order_by(func.count(AnalyticsEvent.id).desc())
                .limit(top_n)
            )).all()

            # 批量查用户名
            tg_ids = [r.telegram_id for r in rows]
            user_map: dict[int, str] = {}
            if tg_ids:
                users = (await session.execute(
                    select(User.telegram_id, User.username, User.first_name)
                    .where(User.telegram_id.in_(tg_ids))
                )).all()
                for u in users:
                    name = f"@{u.username}" if u.username else (u.first_name or str(u.telegram_id))
                    user_map[u.telegram_id] = name
    except Exception as exc:
        logger.exception("tool_get_user_ranking failed")
        return f"❌ 获取用户排行失败：{exc}"

    if not rows:
        return f"📊 {label} 暂无用户数据。"

    lines = [f"🏆 {label} 用户活跃排行（Top {top_n}）\n"]
    for rank, row in enumerate(rows, 1):
        name = user_map.get(row.telegram_id, str(row.telegram_id))
        lines.append(f"{rank}. {name} — {row.cnt} 次")
    return "\n".join(lines)


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
            "name": "query_price",
            "description": (
                "查询莫斯科户外类产品价格（卢布/人民币/美元）。"
                "当用户询问某个 SKU/型号的价格、报价、多少钱时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "产品型号或 SKU，如 HT-70LRF、GEH50R",
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["vip", "svip", "vvip"],
                        "description": "价格等级：vip=卢布、svip=卢布+人民币（默认）、vvip=加美元",
                    },
                    "brand": {
                        "type": "string",
                        "description": "品牌名（可选，填写可加快搜索），如 Sytong、Longot、Infiray",
                    },
                },
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_discount",
            "description": (
                "查询 Vandych VIP 折扣码和促销信息。"
                "当用户问折扣、优惠码、促销活动时调用。不传 sku 则列出所有有效折扣。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "产品型号（可选，不填则返回全部折扣列表）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_ranking",
            "description": (
                "查询 Telegram Bot 用户活跃度排行榜（按事件数从多到少）。"
                "当用户问「谁最活跃」「活跃用户排行」「Top 用户」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period_days": {
                        "type": "integer",
                        "description": "统计天数：1=今天（默认）、7=近 7 天、30=近 30 天",
                        "minimum": 1,
                        "maximum": 90,
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "显示前 N 名，默认 10",
                        "minimum": 1,
                        "maximum": 30,
                    },
                },
                "required": [],
            },
        },
    },
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

TOOL_SCHEMAS += [
    {
        "type": "function",
        "function": {
            "name": "tool_create_ae_promo_code",
            "description": "为指定的速卖通（AliExpress）店铺创建买家直接可用的 Promo Code（折扣码）。只能且必须针对特定的【店铺名】（如：主店、配件店），折扣码会自动生成12位随机字母数字，生效时间约为创建指令完成后1小时之内。",
            "parameters": {
                "type": "object",
                "properties": {
                    "store_name": {
                        "type": "string",
                        "description": "速卖通店铺名称或别名（如：主店、配件店、三店等），必须指定。"
                    },
                    "discount_value": {
                        "type": "number",
                        "description": "立减金额，默认货币为美元（USD），如 5.0"
                    },
                    "min_order_amount": {
                        "type": "number",
                        "description": "满减条件门槛金额（如果为空，请求用户补充）。"
                    },
                    "validity_days": {
                        "type": "integer",
                        "description": "折扣的有效期天数。如果用户没有提供，务必通过对话反问获取。"
                    },
                    "total_num": {
                        "type": "integer",
                        "description": "总共发放的名额张数。如果用户没有提供，务必通过对话反问获取。"
                    },
                    "num_per_buyer": {
                        "type": "integer",
                        "description": "每人限领限用几张。如果未提供，务必通过对话反问获取。"
                    }
                },
                "required": ["store_name", "discount_value", "min_order_amount", "validity_days", "total_num", "num_per_buyer"]
            }
        }
    }
]

TOOL_HANDLERS = {
    "get_inventory": tool_get_inventory,
    "get_daily_report": tool_get_daily_report,
    "query_price": tool_query_price,
    "get_discount": tool_get_discount,
    "get_user_ranking": tool_get_user_ranking,
    "search_sn": tool_search_sn,
    "check_repair": tool_check_repair,
    "tool_create_ae_promo_code": tool_create_ae_promo_code,
}
