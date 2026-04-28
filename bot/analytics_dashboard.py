"""Web dashboard for bot usage analytics."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from aiohttp import web
from sqlalchemy import func, select

from bot.config import settings
from bot.logging_config import setup_logging
from bot.models import async_session
from bot.models.analytics import AnalyticsEvent
from bot.models.user import User

logger = logging.getLogger(__name__)

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

DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>A-BF Bot 用户埋点 Dashboard</title>
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
    header h1 {
      margin: 0 0 4px;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
    }
    header p { margin: 0; color: #b9c2d3; }
    main { max-width: 1280px; margin: 0 auto; padding: 20px; }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 16px;
    }
    select, input, button {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 0 10px;
      color: var(--text);
    }
    input { min-width: 240px; }
    button {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
      cursor: pointer;
      font-weight: 600;
    }
    .status { color: var(--muted); margin-left: auto; }
    .grid { display: grid; gap: 14px; }
    .cards { grid-template-columns: repeat(5, minmax(150px, 1fr)); }
    .two { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 14px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: 0 1px 2px rgba(16, 24, 39, 0.04);
    }
    .card .label { color: var(--muted); font-size: 13px; }
    .card .value { font-size: 26px; font-weight: 750; margin-top: 4px; }
    .card .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
    h2 { margin: 0 0 12px; font-size: 16px; }
    .bar-row {
      display: grid;
      grid-template-columns: minmax(110px, 170px) 1fr 64px;
      gap: 10px;
      align-items: center;
      margin: 8px 0;
    }
    .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #293244;
    }
    .bar-track {
      height: 12px;
      background: #edf1f7;
      border-radius: 999px;
      overflow: hidden;
    }
    .bar {
      height: 100%;
      min-width: 2px;
      background: var(--accent);
      border-radius: 999px;
    }
    .bar.alt { background: var(--accent-2); }
    .count { text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 8px 6px; border-bottom: 1px solid var(--line); text-align: left; }
    th { color: var(--muted); font-size: 12px; font-weight: 650; }
    td { font-variant-numeric: tabular-nums; }
    .empty { color: var(--muted); padding: 18px 0; text-align: center; }
    .error { color: #b42318; font-weight: 600; }
    @media (max-width: 980px) {
      .cards, .two { grid-template-columns: 1fr; }
      .status { width: 100%; margin-left: 0; }
    }
  </style>
</head>
<body>
  <header>
    <h1>A-BF Telegram Bot 用户埋点</h1>
    <p>查看客户使用路径、模块热度、每日趋势和用户活跃度。</p>
  </header>
  <main>
    <div class="toolbar">
      <label>时间范围
        <select id="days">
          <option value="1">今天</option>
          <option value="7" selected>近 7 天</option>
          <option value="14">近 14 天</option>
          <option value="30">近 30 天</option>
          <option value="90">近 90 天</option>
        </select>
      </label>
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
      <div class="panel"><h2>模块热度</h2><div id="moduleBars"></div></div>
      <div class="panel"><h2>功能动作排行</h2><div id="actionBars"></div></div>
    </section>

    <section class="grid two">
      <div class="panel"><h2>每日趋势</h2><div id="dailyBars"></div></div>
      <div class="panel"><h2>语言分布</h2><div id="languageBars"></div></div>
    </section>

    <section class="grid two">
      <div class="panel">
        <h2>用户排行</h2>
        <table>
          <thead><tr><th>用户</th><th>TGID</th><th>事件</th><th>最后访问</th></tr></thead>
          <tbody id="topUsers"></tbody>
        </table>
      </div>
      <div class="panel">
        <h2>最近事件</h2>
        <table>
          <thead><tr><th>时间</th><th>TGID</th><th>事件</th><th>结果</th></tr></thead>
          <tbody id="recentEvents"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const fmt = new Intl.NumberFormat('zh-CN');

    function setText(id, value) {
      $(id).textContent = Number.isFinite(value) ? fmt.format(value) : '-';
    }

    function makeBars(el, rows, colorClass='') {
      if (!rows || rows.length === 0) {
        el.innerHTML = '<div class="empty">暂无数据</div>';
        return;
      }
      const max = Math.max(...rows.map(r => r.count), 1);
      el.innerHTML = rows.map(row => {
        const width = Math.max(2, Math.round(row.count / max * 100));
        return `<div class="bar-row" title="${escapeHtml(row.name)}">
          <div class="name">${escapeHtml(row.name)}</div>
          <div class="bar-track"><div class="bar ${colorClass}" style="width:${width}%"></div></div>
          <div class="count">${fmt.format(row.count)}</div>
        </div>`;
      }).join('');
    }

    function fillTable(el, rows, renderer) {
      if (!rows || rows.length === 0) {
        el.innerHTML = '<tr><td colspan="4" class="empty">暂无数据</td></tr>';
        return;
      }
      el.innerHTML = rows.map(renderer).join('');
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[c]));
    }

    function shortTime(value) {
      if (!value) return '-';
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return value;
      return d.toLocaleString('zh-CN', { hour12: false });
    }

    async function load() {
      $('status').textContent = '加载中...';
      $('status').className = 'status';
      const days = $('days').value;
      const token = $('token').value.trim();
      localStorage.setItem('analyticsToken', token);
      const url = new URL('/api/summary', window.location.origin);
      url.searchParams.set('days', days);

      const headers = token ? { 'X-Analytics-Token': token } : {};
      const res = await fetch(url, { headers });
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
      setText('totalEvents', data.summary.total_events);
      setText('activeUsers', data.summary.active_users);
      setText('callbacks', data.summary.callbacks);
      setText('messages', data.summary.messages);
      setText('recentUsers', data.summary.recent_active_users);
      makeBars($('moduleBars'), data.modules);
      makeBars($('actionBars'), data.actions, 'alt');
      makeBars($('dailyBars'), data.daily.map(r => ({ name: r.day, count: r.events })));
      makeBars($('languageBars'), data.languages);
      fillTable($('topUsers'), data.top_users, (u) => `<tr>
        <td>${escapeHtml(u.display_name)}</td><td>${escapeHtml(u.telegram_id)}</td>
        <td>${fmt.format(u.count)}</td><td>${shortTime(u.last_seen)}</td>
      </tr>`);
      fillTable($('recentEvents'), data.recent_events, (e) => `<tr>
        <td>${shortTime(e.created_at)}</td><td>${escapeHtml(e.telegram_id)}</td>
        <td>${escapeHtml(e.event_name)}</td><td>${escapeHtml(e.outcome || '-')}</td>
      </tr>`);
      $('status').textContent = `已更新：${shortTime(new Date().toISOString())}`;
    }

    $('refresh').addEventListener('click', () => load().catch(err => {
      $('status').textContent = '加载失败：' + err.message;
      $('status').className = 'status error';
    }));
    $('days').addEventListener('change', () => $('refresh').click());
    $('token').value = localStorage.getItem('analyticsToken') || '';
    $('refresh').click();
  </script>
</body>
</html>
"""


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


def _days(request: web.Request) -> int:
    try:
        value = int(request.query.get("days", "7"))
    except ValueError:
        value = 7
    return max(1, min(value, 90))


def _since(days: int) -> datetime:
    start_day = date.today() - timedelta(days=days - 1)
    return datetime.combine(start_day, time.min)


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


async def index(_: web.Request) -> web.Response:
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def summary(request: web.Request) -> web.Response:
    if not _authorized(request):
        return _json_error("unauthorized", 401)

    days = _days(request)
    since = _since(days)
    recent_since = datetime.utcnow() - timedelta(minutes=15)

    async with async_session() as session:
        total_events = await session.scalar(
            select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.created_at >= since)
        )
        active_users = await session.scalar(
            select(func.count(func.distinct(AnalyticsEvent.telegram_id))).where(
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.telegram_id.is_not(None),
            )
        )
        callbacks = await session.scalar(
            select(func.count(AnalyticsEvent.id)).where(
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.event_type == "callback",
            )
        )
        messages = await session.scalar(
            select(func.count(AnalyticsEvent.id)).where(
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.event_type == "message",
            )
        )
        recent_active_users = await session.scalar(
            select(func.count(func.distinct(AnalyticsEvent.telegram_id))).where(
                AnalyticsEvent.created_at >= recent_since,
                AnalyticsEvent.telegram_id.is_not(None),
            )
        )

        modules = await _count_by(session, AnalyticsEvent.module, since, 12, _module_label)
        languages = await _count_by(session, AnalyticsEvent.language, since, 8, _language_label)
        actions = await _top_actions(session, since)
        daily = await _daily(session, since, days)
        top_users = await _top_users(session, since)
        recent_events = await _recent_events(session)

    return web.json_response(
        {
            "days": days,
            "summary": {
                "total_events": int(total_events or 0),
                "active_users": int(active_users or 0),
                "callbacks": int(callbacks or 0),
                "messages": int(messages or 0),
                "recent_active_users": int(recent_active_users or 0),
            },
            "modules": modules,
            "actions": actions,
            "daily": daily,
            "languages": languages,
            "top_users": top_users,
            "recent_events": recent_events,
        }
    )


async def _count_by(
    session: Any,
    column: Any,
    since: datetime,
    limit: int,
    label_fn: Any | None = None,
) -> list[dict[str, Any]]:
    name = func.coalesce(column, "unknown").label("name")
    count = func.count(AnalyticsEvent.id).label("count")
    result = await session.execute(
        select(name, count)
        .where(AnalyticsEvent.created_at >= since)
        .group_by(name)
        .order_by(count.desc())
        .limit(limit)
    )
    rows: list[dict[str, Any]] = []
    for row in result.mappings():
        code = str(row["name"])
        rows.append({
            "name": label_fn(code) if label_fn else code,
            "code": code,
            "count": int(row["count"]),
        })
    return rows


async def _top_actions(session: Any, since: datetime) -> list[dict[str, Any]]:
    count = func.count(AnalyticsEvent.id).label("count")
    result = await session.execute(
        select(AnalyticsEvent.module, AnalyticsEvent.action, count)
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.module, AnalyticsEvent.action)
        .order_by(count.desc())
        .limit(16)
    )
    rows: list[dict[str, Any]] = []
    for module, action, event_count in result:
        module_code = str(module or "unknown")
        action_code = str(action or "unknown")
        rows.append({
            "name": _action_label(module_code, action_code),
            "code": f"{module_code}.{action_code}",
            "count": int(event_count),
        })
    return rows


async def _daily(session: Any, since: datetime, days: int) -> list[dict[str, Any]]:
    day_col = func.date(AnalyticsEvent.created_at).label("day")
    events = func.count(AnalyticsEvent.id).label("events")
    users = func.count(func.distinct(AnalyticsEvent.telegram_id)).label("users")
    result = await session.execute(
        select(day_col, events, users)
        .where(AnalyticsEvent.created_at >= since)
        .group_by(day_col)
        .order_by(day_col)
    )

    found = {
        str(row["day"]): {"events": int(row["events"]), "users": int(row["users"])}
        for row in result.mappings()
    }
    start_day = since.date()
    rows: list[dict[str, Any]] = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        key = day.isoformat()
        values = found.get(key, {"events": 0, "users": 0})
        rows.append({"day": key, **values})
    return rows


async def _top_users(session: Any, since: datetime) -> list[dict[str, Any]]:
    count = func.count(AnalyticsEvent.id).label("count")
    last_seen = func.max(AnalyticsEvent.created_at).label("last_seen")
    result = await session.execute(
        select(
            AnalyticsEvent.telegram_id,
            func.max(User.username).label("username"),
            func.max(User.first_name).label("first_name"),
            func.max(User.last_name).label("last_name"),
            count,
            last_seen,
        )
        .outerjoin(User, User.telegram_id == AnalyticsEvent.telegram_id)
        .where(
            AnalyticsEvent.created_at >= since,
            AnalyticsEvent.telegram_id.is_not(None),
        )
        .group_by(AnalyticsEvent.telegram_id)
        .order_by(count.desc())
        .limit(20)
    )
    rows: list[dict[str, Any]] = []
    for row in result.mappings():
        name_parts = [part for part in (row["first_name"], row["last_name"]) if part]
        display_name = (" ".join(name_parts) or row["username"] or str(row["telegram_id"]))
        if row["username"]:
            display_name = f"{display_name} (@{row['username']})"
        rows.append({
            "telegram_id": row["telegram_id"],
            "display_name": display_name,
            "count": int(row["count"]),
            "last_seen": _dt(row["last_seen"]),
        })
    return rows


async def _recent_events(session: Any) -> list[dict[str, Any]]:
    result = await session.execute(
        select(
            AnalyticsEvent.created_at,
            AnalyticsEvent.telegram_id,
            AnalyticsEvent.module,
            AnalyticsEvent.action,
            AnalyticsEvent.event_name,
            AnalyticsEvent.event_data,
        )
        .order_by(AnalyticsEvent.created_at.desc())
        .limit(40)
    )
    return [
        {
            "created_at": _dt(row["created_at"]),
            "telegram_id": row["telegram_id"],
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


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/summary", summary)
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
