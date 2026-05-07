"""速卖通店铺 Cookie 管理后台。

提供简单的 Web 界面，用于查看和更新各速卖通店铺的登录 Cookie。

Endpoints:
    GET  /            HTML 管理页面
    GET  /health      healthcheck
    GET  /api/stores  返回所有店铺列表（JSON）
    POST /api/stores  新增或更新店铺 Cookie（JSON body: {store_name, cookie}）
    DELETE /api/stores/{store_name}  删除店铺记录
"""

from __future__ import annotations

import logging

from aiohttp import web
from sqlalchemy import select

from bot.config import settings
from bot.logging_config import setup_logging
from bot.models import async_session
from bot.models.ae_store_cookie import AEStoreCookie

logger = logging.getLogger(__name__)

# ── Auth ──────────────────────────────────────────────────────


def _check_token(request: web.Request) -> bool:
    token = settings.ae_cookie_dashboard_token
    if not token:
        return True
    return (
        request.query.get("token") == token
        or request.headers.get("X-Dashboard-Token") == token
    )


def _require_token(handler):
    async def wrapper(request: web.Request) -> web.Response:
        if not _check_token(request):
            raise web.HTTPForbidden(text="Invalid or missing token")
        return await handler(request)
    return wrapper


# ── API ──────────────────────────────────────────────────────


@_require_token
async def api_list_stores(request: web.Request) -> web.Response:
    async with async_session() as session:
        rows = (await session.execute(
            select(AEStoreCookie).order_by(AEStoreCookie.store_name)
        )).scalars().all()

    data = []
    for row in rows:
        cookie = row.cookie or ""
        has_tk = "_m_h5_tk=" in cookie
        # 只展示 cookie 长度，不暴露原文
        data.append({
            "store_name": row.store_name,
            "has_cookie": bool(cookie),
            "has_tk": has_tk,
            "cookie_len": len(cookie),
            "updated_at": row.updated_at.isoformat() if row.updated_at else (
                row.created_at.isoformat() if row.created_at else ""
            ),
        })
    return web.json_response(data)


@_require_token
async def api_upsert_store(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON body")

    store_name = (body.get("store_name") or "").strip()
    cookie = (body.get("cookie") or "").strip()
    if not store_name:
        raise web.HTTPBadRequest(text="store_name is required")
    if not cookie:
        raise web.HTTPBadRequest(text="cookie is required")

    async with async_session() as session:
        row = await session.scalar(
            select(AEStoreCookie).where(AEStoreCookie.store_name == store_name)
        )
        if row:
            row.cookie = cookie
            action = "updated"
        else:
            session.add(AEStoreCookie(store_name=store_name, cookie=cookie))
            action = "created"
        await session.commit()

    logger.info("[ae-cookie-dash] %s store=%s cookie_len=%d", action, store_name, len(cookie))
    return web.json_response({"ok": True, "action": action, "store_name": store_name})


@_require_token
async def api_delete_store(request: web.Request) -> web.Response:
    store_name = request.match_info["store_name"]
    async with async_session() as session:
        row = await session.scalar(
            select(AEStoreCookie).where(AEStoreCookie.store_name == store_name)
        )
        if not row:
            raise web.HTTPNotFound(text=f"Store '{store_name}' not found")
        await session.delete(row)
        await session.commit()

    logger.info("[ae-cookie-dash] deleted store=%s", store_name)
    return web.json_response({"ok": True, "store_name": store_name})


async def health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


# ── HTML ─────────────────────────────────────────────────────

def _html(token: str) -> str:
    token_js = token.replace("'", "\\'")
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>速卖通 Cookie 管理</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f5f6fa; color: #333; min-height: 100vh; }}
  .header {{ background: #1a73e8; color: #fff; padding: 16px 24px;
             display: flex; align-items: center; gap: 12px; }}
  .header h1 {{ font-size: 18px; font-weight: 600; }}
  .badge {{ background: rgba(255,255,255,.2); border-radius: 12px;
            padding: 2px 10px; font-size: 12px; }}
  .container {{ max-width: 1000px; margin: 24px auto; padding: 0 16px; }}
  .card {{ background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
           padding: 20px; margin-bottom: 20px; }}
  .card h2 {{ font-size: 15px; font-weight: 600; margin-bottom: 16px;
              color: #1a73e8; border-bottom: 1px solid #e8eaed; padding-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f8f9fa; padding: 10px 12px; text-align: left;
        font-weight: 600; color: #5f6368; border-bottom: 2px solid #e8eaed; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #f1f3f4; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #f8f9fa; }}
  .tag {{ display: inline-block; border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}
  .tag-ok {{ background: #e6f4ea; color: #137333; }}
  .tag-warn {{ background: #fce8e6; color: #c5221f; }}
  .tag-info {{ background: #e8f0fe; color: #1967d2; }}
  .btn {{ padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
          font-size: 13px; font-weight: 500; transition: opacity .15s; }}
  .btn:hover {{ opacity: .85; }}
  .btn-danger {{ background: #fce8e6; color: #c5221f; }}
  .btn-primary {{ background: #1a73e8; color: #fff; }}
  .btn-sm {{ padding: 4px 10px; font-size: 12px; }}
  .form-row {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }}
  .form-row label {{ font-size: 13px; font-weight: 500; color: #5f6368;
                     display: block; margin-bottom: 4px; }}
  input[type=text] {{ border: 1px solid #dadce0; border-radius: 6px;
                      padding: 8px 12px; font-size: 13px; width: 100%; }}
  input[type=text]:focus {{ outline: none; border-color: #1a73e8; box-shadow: 0 0 0 2px rgba(26,115,232,.15); }}
  .field-name {{ flex: 0 0 200px; }}
  .field-cookie {{ flex: 1 1 400px; }}
  .msg {{ padding: 10px 14px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; display: none; }}
  .msg-ok {{ background: #e6f4ea; color: #137333; }}
  .msg-err {{ background: #fce8e6; color: #c5221f; }}
  .ts {{ color: #9aa0a6; font-size: 12px; }}
  #loading {{ color: #9aa0a6; font-size: 13px; padding: 20px 0; text-align: center; }}
</style>
</head>
<body>
<div class="header">
  <h1>速卖通 Cookie 管理</h1>
  <span class="badge">AliExpress</span>
</div>
<div class="container">

  <!-- 新增 / 更新 -->
  <div class="card">
    <h2>新增 / 更新店铺 Cookie</h2>
    <div id="formMsg" class="msg"></div>
    <div class="form-row">
      <div class="field-name">
        <label>店铺名称</label>
        <input type="text" id="storeName" placeholder="如 botterrun">
      </div>
      <div class="field-cookie">
        <label>Cookie（完整字符串）</label>
        <input type="text" id="cookieVal" placeholder="cna=xxx; _m_h5_tk=xxx; ...">
      </div>
    </div>
    <button class="btn btn-primary" onclick="upsertStore()">保存</button>
  </div>

  <!-- 店铺列表 -->
  <div class="card">
    <h2>已绑定店铺</h2>
    <div id="loading">加载中…</div>
    <table id="storeTable" style="display:none">
      <thead>
        <tr>
          <th>店铺名称</th>
          <th>Cookie 状态</th>
          <th>_m_h5_tk</th>
          <th>Cookie 长度</th>
          <th>最后更新</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody id="storeBody"></tbody>
    </table>
  </div>
</div>

<script>
const TOKEN = '{token_js}';
const qs = TOKEN ? '?token=' + TOKEN : '';

function showMsg(id, text, ok) {{
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'msg ' + (ok ? 'msg-ok' : 'msg-err');
  el.style.display = 'block';
  setTimeout(() => el.style.display = 'none', 4000);
}}

async function loadStores() {{
  try {{
    const r = await fetch('/api/stores' + qs);
    const data = await r.json();
    const tbody = document.getElementById('storeBody');
    tbody.innerHTML = '';
    if (!data.length) {{
      tbody.innerHTML = '<tr><td colspan="6" style="color:#9aa0a6;text-align:center">暂无数据</td></tr>';
    }} else {{
      data.forEach(s => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${{s.store_name}}</strong></td>
          <td>${{s.has_cookie
            ? '<span class="tag tag-ok">✓ 已绑定</span>'
            : '<span class="tag tag-warn">✗ 未绑定</span>'}}</td>
          <td>${{s.has_tk
            ? '<span class="tag tag-ok">有效</span>'
            : '<span class="tag tag-warn">缺失</span>'}}</td>
          <td><span class="tag tag-info">${{s.cookie_len}} 字符</span></td>
          <td class="ts">${{s.updated_at ? s.updated_at.replace('T',' ').slice(0,19) : '—'}}</td>
          <td>
            <button class="btn btn-danger btn-sm" onclick="deleteStore('${{s.store_name}}')">删除</button>
          </td>`;
        tbody.appendChild(tr);
      }});
    }}
    document.getElementById('loading').style.display = 'none';
    document.getElementById('storeTable').style.display = '';
  }} catch(e) {{
    document.getElementById('loading').textContent = '加载失败：' + e;
  }}
}}

async function upsertStore() {{
  const name = document.getElementById('storeName').value.trim();
  const cookie = document.getElementById('cookieVal').value.trim();
  if (!name || !cookie) {{ showMsg('formMsg', '店铺名称和 Cookie 不能为空', false); return; }}
  try {{
    const r = await fetch('/api/stores' + qs, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{store_name: name, cookie}})
    }});
    const data = await r.json();
    if (data.ok) {{
      showMsg('formMsg', `✅ 已${{data.action === 'created' ? '新增' : '更新'}}店铺：${{name}}`, true);
      document.getElementById('storeName').value = '';
      document.getElementById('cookieVal').value = '';
      loadStores();
    }} else {{
      showMsg('formMsg', '操作失败', false);
    }}
  }} catch(e) {{
    showMsg('formMsg', '请求错误：' + e, false);
  }}
}}

async function deleteStore(name) {{
  if (!confirm(`确定删除店铺「${{name}}」的 Cookie 记录？`)) return;
  try {{
    const r = await fetch('/api/stores/' + encodeURIComponent(name) + qs, {{method: 'DELETE'}});
    const data = await r.json();
    if (data.ok) {{ loadStores(); }}
  }} catch(e) {{
    alert('删除失败：' + e);
  }}
}}

loadStores();
</script>
</body>
</html>"""


@_require_token
async def index(request: web.Request) -> web.Response:
    token = settings.ae_cookie_dashboard_token
    return web.Response(text=_html(token), content_type="text/html", charset="utf-8")


# ── App factory ───────────────────────────────────────────────


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/stores", api_list_stores)
    app.router.add_post("/api/stores", api_upsert_store)
    app.router.add_delete("/api/stores/{store_name}", api_delete_store)
    return app


def main() -> None:
    setup_logging(settings.log_level, settings.log_format)
    port = settings.ae_cookie_dashboard_port
    logger.info("[ae-cookie-dash] 启动，端口 %d", port)
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port, access_log=None)


if __name__ == "__main__":
    main()
