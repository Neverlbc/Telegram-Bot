# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

A-BF 跨境电商内部系统，包含两条主线：

1. **Telegram Bot**（对外）— 基于 aiogram 3.x，面向中俄跨境电商客户。核心功能：莫斯科现货/价格查询（普通/VIP/SVIP/VVIP 四级）、俄罗斯服务中心（设备检修追踪）、晨夜俱乐部、Vandych VIP 隐藏菜单、用户埋点 dashboard。支持中/英/俄三语。
2. **企业微信 AI 助理**（对内）— 基于长连接 WebSocket + DeepSeek tool-calling 的内部 agent，支持自然语言查询库存/价格/日报/SN验真/检修状态，并可直接创建速卖通折扣码。

已部署生产环境，MySQL + Redis + Docker Compose 多服务编排。

## 常用命令

```bash
# Telegram Bot 启动
python -m bot                   # 开发模式（Polling）
python -m bot --webhook         # 生产模式（Webhook）

# 独立脚本
python -m bot.sync              # 手动触发一次库存同步
python -m bot.wecom             # 企业微信 agent（通常由 Docker 启动）
python -m bot.analytics_dashboard   # 分析看板（通常由 Docker 启动）
python -m bot.ae_cookie_dashboard   # AE Cookie 管理后台（通常由 Docker 启动）

# 测试
pytest                          # 全部测试
pytest tests/test_callbacks.py -v
pytest tests/test_config.py -v

# 代码质量
ruff check bot/                 # lint
ruff format bot/                # 格式化
mypy bot/                       # 类型检查

# Docker（服务器）
docker compose up -d --build              # 构建并启动全部服务
docker compose up -d --build bot          # 局部重建 Telegram bot
docker compose up -d --build wecom-agent  # 局部重建企业微信 agent
docker compose up -d --build ae-cookie-dashboard  # 局部重建 Cookie 管理后台
docker compose logs -f bot
docker compose logs -f wecom-agent
docker compose logs -f inventory-sync
docker compose logs -f repair-monitor
docker compose logs -f analytics-dashboard
docker compose logs -f ae-cookie-dashboard
docker compose restart bot      # 仅重启（不重建镜像）
```

## 架构概览

```
bot/
├── __main__.py              # Telegram Bot 入口，解析参数决定 Polling/Webhook
├── config.py                # pydantic Settings，从 .env 加载所有配置
├── app.py                   # Bot、Dispatcher、中间件、路由注册
├── repair_monitor.py        # 独立脚本：轮询检修状态变更并推送通知
├── sync.py                  # 独立脚本：手动触发库存同步
├── analytics_dashboard.py   # 独立 aiohttp Web 服务：用户埋点看板（端口 8088）
├── ae_cookie_dashboard.py   # 独立 aiohttp Web 服务：速卖通 Cookie 管理后台（端口 8089）
│
├── wecom/                   # 企业微信智能机器人（长连接 WebSocket）
│   ├── __main__.py          #   入口：python -m bot.wecom
│   │                        #   处理文本/txt/docx 消息，/update_cookie 指令，并发控制
│   ├── client.py            #   WebSocket 客户端：连接/订阅/心跳/重连/文件下载
│   ├── tools.py             #   LLM 可调用工具（9个，见下方工具清单）
│   └── llm.py               #   DeepSeek tool-calling（最多 3 轮循环）
│
├── handlers/                # aiogram Router，按功能拆分
│   ├── start.py             #   /start、语言选择
│   ├── menu.py              #   /menu、/cancel、主菜单、NavCallback 路由
│   ├── hidden_entries.py    #   所有隐藏密码入口的统一路由（注册在最前）
│   ├── inventory.py         #   莫斯科现货 + VIP/SVIP/VVIP 价格查询
│   ├── service_center.py    #   A-BF 俄罗斯服务中心
│   ├── club.py              #   A-BF 晨夜俱乐部（URL 跳转）
│   ├── vip.py               #   Vandych VIP 隐藏菜单
│   └── settings.py          #   用户设置、/lang、/help
├── keyboards/
│   ├── callbacks.py         # CallbackData 工厂
│   └── inline.py            # InlineKeyboard 构建器
├── middlewares/
│   ├── throttle.py          # 频率限制（Redis）
│   ├── db.py                # DB 会话注入
│   ├── user.py              # 用户 upsert
│   ├── i18n.py              # 语言注入（lang 参数）
│   └── analytics.py         # 埋点中间件，每个 update 写一条 AnalyticsEvent
│
├── models/                  # SQLAlchemy 2.0 async ORM 实体
│   ├── user.py              # User（telegram_id/username/language/is_admin）
│   ├── analytics.py         # AnalyticsEvent（事件流）
│   ├── analytics_annotation.py  # AnalyticsAnnotation（活动节点标注）
│   └── ae_store_cookie.py   # AEStoreCookie（速卖通店铺 Cookie + channel_id）
│
└── services/
    ├── outdoor_sheets.py    # 莫斯科户外库存（gspread + Redis 缓存）
    ├── outdoor_prices.py    # 价格表读取（每个品牌一个 tab，多语言列）
    ├── outdoor_sku_aliases.py  # JST↔KYB SKU 映射
    ├── inventory_tiers.py   # 四级权限定义（public/vip/svip/vvip）
    ├── inventory_sync.py    # 库存同步编排（KYB tocUsableQty - JST order_lock）
    ├── jushuitan.py         # 聚水潭 ERP 客户端（含 token 自动获取）
    ├── kuayunbao.py         # 跨运宝 WMS 客户端
    ├── service_center_sheet.py  # 服务中心检修表（CSV 读取 + Redis 缓存）
    ├── sn_sheet.py          # SN 序列号跨品牌 tab 查询
    ├── discount_sheet.py    # VIP 折扣表（gspread + CSV 双路径）
    ├── aliexpress_mtop.py   # 速卖通网页端 MTOP API 客户端（Cookie 鉴权，多店铺）
    ├── sheets_writer.py     # Google Sheets 写回
    ├── translation.py       # DeepSeek 俄→英翻译（描述列用，Redis 缓存 30 天）
    ├── hidden_access.py     # 隐藏菜单 access token TTL 管理
    ├── notification.py      # 推送通知
    └── analytics.py         # 埋点事件 snapshot 构建
```

**Telegram Bot 请求处理链路：**
`Telegram → Dispatcher → 中间件（throttle → db → user → i18n → analytics）→ Router → Handler → Service → Sheets / Redis / 通知`

**Router 注册顺序（app.py）：**
`start → hidden_entries → menu → inventory → service_center → settings → vip`

## Telegram Bot 菜单结构

```
公开主菜单
├── 🔍 莫斯科现货查询     → inventory.py
├── 🛠 A-BF 俄罗斯服务中心 → service_center.py
├── 🌙 A-BF 晨夜俱乐部    → URL 按钮（club_tg_link）
└── ⚙️ 设置              → 语言切换面板

隐藏入口（直接发文本，handlers/hidden_entries.py 统一捕获）
├── VIP_INVENTORY_PASSWORD   → VIP 库存隐藏菜单
├── SVIP_INVENTORY_PASSWORD  → SVIP 库存 + 价格查询
├── VVIP_INVENTORY_PASSWORD  → VVIP 库存 + 价格查询（含美元）
├── SERVICE_ADMIN_PASSWORD   → 服务中心管理后台
└── VANDYCH_PASSWORD         → Vandych VIP 隐藏菜单
```

## 企业微信 AI 助理（bot/wecom/）

**面向内部团队**的协同 agent，长连接 WebSocket（无需公网 HTTPS 回调）。

### 连接协议
- WSS 连接 `wss://openws.work.weixin.qq.com`
- 发 `aibot_subscribe` 帧（含 bot_id + secret）完成鉴权
- 每 30 秒发一次业务层心跳 `aibot_ping`（不能用 WebSocket 协议层 ping，会触发 1002 错误）
- 收到 `aibot_msg_callback` → 触发消息处理
- 收到 `aibot_event_callback` → 触发事件处理（进入会话发欢迎语）

### 回复机制（重要）
- 回复命令：`aibot_respond_msg`（不是 `aibot_respond_stream_msg`）
- `headers.req_id` 必须与原始消息相同，服务端用此关联响应
- `body` 只包含 `{msgtype: "stream", stream: {id, content, finish}}`
- 流程：收到消息 → 立即发 `finish=false` 占位帧（"处理中..."）→ LLM 完成后发 `finish=true` 替换内容
- 并发控制：同一用户同时只处理一条消息（`_user_active` 字典追踪），避免 LLM 堆积

### 消息类型支持
| msgtype | 处理方式 |
|---|---|
| `text` | 直接提取文本内容 |
| `attachment` / `file` | 下载文件，支持 `.txt` 和 `.docx` 解析 |
| `docmsg` | 判断是否含 fileid，有则下载解析 .docx，否则提示用户改发文件 |
| `.doc` | 提示用户改存为 .docx |

### 文件下载（client.py）
- 发 `aibot_download_media` 帧请求下载
- 收 `aibot_download_media_data` 帧，base64 分块拼接
- `pending_downloads` 字典管理并发下载，Future 异步等待结果

### /update_cookie 指令
在企微对话中发送以下格式直接更新速卖通 Cookie（绕过 LLM 即时执行）：
```
/update_cookie 店铺名 你的Cookie字符串
```
Cookie 太长时可放入 `.txt` 或 `.docx` 文件第一行写指令，正文粘贴 cookie 发送。

### LLM 工具清单（tools.py）

| 工具名 | 功能 | 关键参数 |
|---|---|---|
| `get_inventory` | 莫斯科户外库存清单（按品牌分组） | `tier` (public/vip/svip/vvip) |
| `get_daily_report` | Telegram Bot 用户埋点日报 | `period_days` (1-90) |
| `query_price` | 户外产品价格（RUB/CNY/USD） | `sku`, `tier`, `brand` |
| `get_discount` | Vandych VIP 折扣码/促销信息 | `sku` (可选，模糊搜索) |
| `get_user_ranking` | TG Bot 活跃用户排行 | `period_days`, `top_n` |
| `search_sn` | 跨品牌 SN 序列号验真 | `sn` |
| `check_repair` | 服务中心检修状态（CDEK/SN查询） | `query` |
| `list_ae_stores` | 列出数据库已绑定 Cookie 的速卖通店铺 | — |
| `create_ae_promo_code` | 创建速卖通折扣码（通常 5-15 分钟生效） | `store_name`, `discount_value`, `min_order_amount`, `validity_days`, `total_num`, `num_per_buyer`, `product_ids`（可选） |

创建折扣码时：若用户未指定店铺 → 先调 `list_ae_stores` 展示可选列表 → 用户选择 → 询问适用全部产品还是部分产品（部分则要求提供产品ID，逗号分隔）→ 收集缺少参数 → 调用创建。若指定产品，创建成功后自动调用 `mtop.global.merchant.promotion.ae.voucher.product.save` 绑定产品，失败则返回手动操作的后台 URL。

## 速卖通 Cookie 管理

### 数据库模型（AEStoreCookie）
表名 `ae_store_cookies`，字段：
- `store_name`：店铺名称（唯一索引）
- `cookie`：完整 Cookie 字符串
- `channel_id`：速卖通渠道 ID（默认 `238299`，每个卖家账号固定，从促销页 URL `channelId=xxx` 获取）

### MTOPClient（aliexpress_mtop.py）
- 使用浏览器 Cookie 调用速卖通网页端 MTOP API
- 签名算法：`MD5(token&t&appKey&data)`，`token` 从 `_m_h5_tk` 提取
- 自动续命：检测到响应 Cookie 中有新 `_m_h5_tk` 时，自动回写数据库并重试请求
- Session 过期检测：`ret` 字段含 `SESSION_EXPIRED`/`TOKEN_EMPTY` 等关键词时抛出 `ValueError("SESSION_EXPIRED")`
- 工厂方法：`await MTOPClient.create(store_name)` 从数据库加载 cookie + channel_id

### Cookie 管理后台（端口 8089）
- 访问：`http://服务器IP:8089?token=xxx`（token 由 `AE_COOKIE_DASHBOARD_TOKEN` 控制，空则无鉴权）
- 功能：新增/更新店铺 Cookie、查看绑定状态（_m_h5_tk 有效性、Cookie 长度）、删除店铺
- Channel ID 在表单中可见和编辑，数据库透明存储

### 折扣码参数配置
- `codeScope: "public"`（通用/可共享）
- `couponChannelType: "1"`（IM, CRM, Feed, games 渠道）
- `channelId`：从数据库 `ae_store_cookies.channel_id` 读取，每店铺不同
- 活动名称默认：`跨境机器人创建`

## 库存同步公式（关键）

`inventory_sync.py` 每 5 分钟跑一次，公式：

```
QTYS = KYB 俄罗斯仓 tocUsableQty − JST 俄罗斯仓 order_lock
```

注意点：
- KYB 必须只统计**俄罗斯仓库**（默认 `RUS2`），不含东莞中转仓 SZW
- KYB 不同 SKU 的 `tocUsableQty` 行为不一致：有的已扣 JST 订单（如 TRS-335LRF），有的没扣（如 GEH50R）。所以要用 `tocUsableQty`，再减 JST `order_lock` 才能保证一致正确
- JST `get_stock_map` 必须**累加**多仓库的 `order_lock`，而不是覆盖
- 配置仓库过滤：`KYB_RUSSIA_WAREHOUSE_CODES=RUS2`（默认）；`JST_RUSSIA_WAREHOUSE_CODE=...`

## 聚水潭 token 管理（jushuitan.py）

本项目应用类型支持 `getInitToken` + 随机 6 位 code 直接拿 access_token，**不需要 OAuth / refresh_token**。

获取顺序：
1. Redis 缓存里未过期的 token
2. `getInitToken` 接口拿新 token（自动缓存 2 小时）
3. 兜底使用 `JST_ACCESS_TOKEN` env（手动粘贴）

调用 API 时若返回 token 失效错误，自动清缓存并重试一次。

## 用户埋点 Dashboard（analytics_dashboard.py）

独立 aiohttp 服务，端口 8088，访问 token 由 `ANALYTICS_DASHBOARD_TOKEN` 控制。

### 数据模型
- `analytics_events`：每个 Telegram update 一条，含 module / action / language / event_data
- `analytics_annotations`：手动录入的活动/大促节点，叠加到趋势图上

### 看板（基于 ECharts）
| 看板 | 切换图表 | 导出 Excel |
|------|---------|-----------|
| 每日趋势（4 线：新增/活跃/点击/价格查询） | 折线/柱状/饼图 | ✓ |
| 语言分布 | 饼图/柱状/折线 | ✓ |
| 模块热度（含上期对比） | 柱状/饼图/折线 | ✓ |
| 会员等级分布 | 饼图/柱状/折线 | ✓ |
| 功能动作排行 | 柱状/饼图/折线 | ✓ |
| 隐藏菜单激活 | 柱状/饼图/折线 | ✓ |
| 用户排行（含等级 badge） | 表格 | ✓ |
| 最近事件流（含用户名） | 表格 | ✓ |
| 活动 / 大促节点标注 | 管理面板（增删改） | — |

### Excel 导出结构
每个导出 = **概览** sheet + **明细** sheet。明细列：
`时间 / TGID / 用户名 / 显示名称 / 等级 / 语言 / 模块 / 动作 / 结果`

### 用户分级
基于全时间窗口的 `hidden_access.password_success` 事件推导：
`vvip > svip > vip > vandych > service_admin > public`

## Docker 服务

| 服务 | 端口 | 说明 |
|------|------|------|
| `bot` | — | Telegram Bot 主应用（polling/webhook），entrypoint 跑 create_all |
| `redis` | — | Redis 7（256MB LRU，AOF 持久化，仅内网） |
| `inventory-sync` | — | 每 5 分钟同步库存，外层 `timeout 240` 防卡死 |
| `repair-monitor` | — | 每 5 分钟轮询检修状态变更 |
| `analytics-dashboard` | 8088 | 用户埋点看板 aiohttp 服务 |
| `ae-cookie-dashboard` | 8089 | 速卖通 Cookie 管理后台 aiohttp 服务 |
| `wecom-agent` | — | 企业微信 AI 助理长连接（仅出站 wss，无端口暴露） |

## 密码 / Token / API Key 配置

| 变量 | 用途 |
|------|------|
| `VIP_INVENTORY_PASSWORD` | VIP 库存隐藏菜单 |
| `SVIP_INVENTORY_PASSWORD` | SVIP 库存 + 价格 |
| `VVIP_INVENTORY_PASSWORD` | VVIP 库存 + 价格（含美元） |
| `SERVICE_ADMIN_PASSWORD` | 服务中心管理后台 |
| `VANDYCH_PASSWORD` | Vandych VIP 菜单 |
| `JST_APP_KEY` / `JST_APP_SECRET` | 聚水潭应用密钥 |
| `JST_ACCESS_TOKEN` | 兜底 access_token（自动获取失败时用） |
| `JST_IS_TEST` | 聚水潭测试环境（True 走 dev-api 域名） |
| `JST_RUSSIA_WAREHOUSE_CODE` | 聚水潭俄罗斯仓库编号（不填则汇总所有仓） |
| `KYB_APP_ID` / `KYB_APP_SECRET` / `KYB_TOKEN` | 跨运宝凭据 |
| `KYB_PLATFORM_CUSTOMER_CODE` | 跨运宝平台客户编码 |
| `KYB_RUSSIA_WAREHOUSE_CODES` | 跨运宝俄罗斯仓库编码列表（默认 `RUS2`） |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（翻译 + 企微 LLM） |
| `DEEPSEEK_MODEL` | DeepSeek 模型（默认 `deepseek-chat`） |
| `DEEPSEEK_API_URL` | DeepSeek chat-completions 端点 |
| `ANALYTICS_DASHBOARD_TOKEN` | 埋点看板访问 token |
| `ANALYTICS_TEST_USERNAMES` | 测试账号 username 列表（不带 @，逗号分隔） |
| `ANALYTICS_TEST_USER_IDS` | 测试账号 telegram_id 列表（数字，逗号分隔） |
| `ADMIN_IDS` | 管理员 telegram_id 列表，也参与测试账号过滤 |
| `WECOM_BOT_ID` | 企业微信智能机器人 BotID |
| `WECOM_BOT_SECRET` | 企业微信智能机器人长连接 Secret |
| `WECOM_BOT_NAME` | 机器人显示名（默认 `A-BF跨境助理`） |
| `WECOM_WS_URL` | 长连接 WSS 网关（默认 `wss://openws.work.weixin.qq.com`） |
| `AE_COOKIE_DASHBOARD_PORT` | AE Cookie 管理后台端口（默认 8089） |
| `AE_COOKIE_DASHBOARD_TOKEN` | AE Cookie 管理后台访问 token（空则无鉴权） |

## Google Sheet 配置

- **私有读写**：gspread + Service Account（`google_credentials.json`），所有客户端设置 60s HTTP 超时
- `.env` 填 Sheet ID：`OUTDOOR_SHEET_ID` / `SERVICE_CENTER_SHEET_ID` / `DISCOUNT_SHEET_ID`

| 用途 | 文件 | 关键常量 |
|------|------|---------|
| 户外库存（按 tier 多 tab） | `services/outdoor_sheets.py` | tab 标题靠 `inventory_tiers.py` |
| 户外价格（每品牌一个 tab） | `services/outdoor_prices.py` | 列角色由 `_column_roles()` 自动识别 |
| 服务中心检修 | `services/service_center_sheet.py` | `COL_CDEK_IN`, `COL_SN`, ... |
| SN 跨品牌 | `services/sn_sheet.py` | 7 个品牌 tab |
| 折扣 | `services/discount_sheet.py` | `COL_MODEL`, `COL_DISCOUNT`, ... |

价格表描述列识别：含 `"опис"` → ru；含 `"描述"` → zh；含 `"description"` → en。

## 数据库约定

- SQLAlchemy 2.0 async（`async_session`）
- **建表用 `Base.metadata.create_all()`**（在 `docker/entrypoint.sh` 里），不用 alembic
- 新增 model 时：① 写 model 文件 ② 在 `docker/entrypoint.sh` 加 import ③ rebuild 容器
- 新增列到已有表：`create_all` 不加列，需手动 `ALTER TABLE`
- alembic 仅作历史保留，有孤儿 revision `38ba7ff1cb39`，执行 `alembic upgrade head` 会报错

## 关键约定

### Handler 组织
- 每模块一个文件 + 独立 `Router`，函数命名 `on_<动作>_<对象>`
- `hidden_entries` 注册在 `start` 之后、其他功能 router 之前，确保密码在 FSM 中也能触发

### 并发 / 异步
- 企微 LLM 处理放入 `asyncio.create_task`，不阻塞 WebSocket 主循环
- 同一用户同时只处理 1 条消息（`_user_active` 字典 + finally 释放）
- 每次 LLM 请求立即发 `finish=False` 占位帧，完成后发 `finish=True` 替换

### 错误处理
- Handler 不 try/except 吞异常
- 外部 API 调用包 try/except，记日志 + 友好提示
- 企微工具函数返回字符串错误（不抛异常），由 LLM 格式化后回复用户

## 部署注意事项

- `.env` 中 `MYSQL_HOST=mysql`、`REDIS_HOST=redis`（Docker 服务名）
- `COMPOSE_PROJECT_NAME=abf-bot-v2`
- 代码更新必须 `docker compose up -d --build <服务名>`，`restart` 不重建镜像
- 新增 model 时必须 rebuild `bot` 容器（entrypoint 跑 create_all 才建新表）
- 新增列到已有表时需在服务器手动执行 `ALTER TABLE`

## 已知历史问题与修复

- **库存数量偏差**：最终方案 `tocUsableQty - JST order_lock` 配合俄罗斯仓过滤
- **库存同步卡死**：gspread 加 60s 超时；Docker 层 `timeout 240` 保底
- **聚水潭 token 过期**：改为 `getInitToken` + 随机 code，不再需要 refresh_token
- **企微 WebSocket 1002 错误**：不能发协议层 ping，改为业务层 `aibot_ping` JSON 帧
- **企微回复不显示**：命令必须用 `aibot_respond_msg`（非 `aibot_respond_stream_msg`），且 `headers.req_id` 必须与原始消息一致
- **速卖通发码权限错误**：不同卖家账号有不同 `channelId`，需按店铺单独配置（从促销页 URL 获取）
- **Dashboard 加载 500**：新增表后 entrypoint 没 import → create_all 跳过；已建立规范：新增 model 必须同步加 import
