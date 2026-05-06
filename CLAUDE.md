# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Telegram 跨境电商客服 Bot — 基于 aiogram 3.x，面向中俄跨境电商场景（已部署生产环境）。
核心功能：莫斯科现货/价格查询（普通/VIP/SVIP/VVIP 四级）、俄罗斯服务中心（设备检修追踪）、晨夜俱乐部、Vandych VIP 隐藏菜单、用户埋点 dashboard。支持中/英/俄三语。

## 常用命令

```bash
# 启动（开发模式，Polling）
python -m bot

# 启动（生产模式，Webhook）
python -m bot --webhook

# 库存同步（手动触发一次）
python -m bot.sync

# 测试
pytest                          # 全部测试
pytest tests/test_callbacks.py -v
pytest tests/test_config.py -v

# 代码质量
ruff check bot/                 # lint
ruff format bot/                # 格式化
mypy bot/                       # 类型检查

# 数据库（项目用 Base.metadata.create_all() 建表，alembic 仅作历史保留）
# 新增 model 必须在 docker/entrypoint.sh 里 import，否则 create_all 不会建表

# Docker（服务器）
docker compose up -d --build    # 构建并启动全部
docker compose up -d --build bot analytics-dashboard  # 局部重建
docker compose logs -f bot
docker compose logs -f inventory-sync
docker compose logs -f repair-monitor
docker compose logs -f analytics-dashboard
docker compose restart bot      # 仅重启（不重建镜像）
```

## 架构概览

```
bot/
├── __main__.py              # 入口，解析参数决定 Polling/Webhook
├── config.py                # pydantic Settings，从 .env 加载配置
├── app.py                   # Bot、Dispatcher、中间件、路由注册
├── repair_monitor.py        # 独立脚本：轮询检修状态变更并推送通知
├── sync.py                  # 独立脚本：手动触发库存同步
├── analytics_dashboard.py   # 独立 aiohttp Web 服务：用户埋点看板（端口 8088）
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
├── models/                  # SQLAlchemy 2.0 async ORM 实体
│   ├── analytics.py         # AnalyticsEvent（事件流）
│   └── analytics_annotation.py  # AnalyticsAnnotation（活动节点标注）
├── services/
│   ├── outdoor_sheets.py    # 莫斯科户外库存（gspread + Redis 缓存）
│   ├── outdoor_prices.py    # 价格表读取（每个品牌一个 tab，多语言列）
│   ├── outdoor_sku_aliases.py  # JST↔KYB SKU 映射
│   ├── inventory_tiers.py   # 四级权限定义（public/vip/svip/vvip）
│   ├── inventory_sync.py    # 库存同步编排（KYB tocUsableQty - JST order_lock）
│   ├── jushuitan.py         # 聚水潭 ERP 客户端（含 token 自动获取）
│   ├── kuayunbao.py         # 跨运宝 WMS 客户端
│   ├── service_center_sheet.py  # 服务中心检修表
│   ├── sn_sheet.py          # SN 序列号跨品牌 tab 查询
│   ├── discount_sheet.py    # VIP 折扣表
│   ├── sheets_writer.py     # Google Sheets 写回
│   ├── translation.py       # DeepSeek 俄→英翻译（描述列用）
│   ├── hidden_access.py     # 隐藏菜单 access token TTL 管理
│   ├── notification.py      # 推送通知
│   └── analytics.py         # 埋点事件 snapshot 构建
├── states/                  # FSM 状态组
└── locales/                 # 占位（多语言用硬编码字典实现）
```

**请求处理链路：** Telegram → Dispatcher → 中间件链（throttle → db → user → i18n → analytics）→ Router → Handler → Service → Sheets / Redis / 通知

**Router 注册顺序（app.py）：**
`start → hidden_entries → menu → inventory → service_center → settings → vip`
（hidden_entries 注册在 menu 之前，确保密码即使在 FSM 中也能触发）

## 菜单结构

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

## 功能模块说明

### 莫斯科现货查询 + 价格查询（inventory.py）
- **公开查询**：读 Outdoor Sheet 普通 tab，仅库存数字
- **VIP/SVIP/VVIP**：输密码后进入对应等级隐藏菜单（`hidden_access.py` 写 access token，TTL=10 分钟）
  - 库存：等级越高读越完整的 tab（`Stock_Outdoor 【VIP/SVIP/VVIP版】`）
  - 价格：SVIP 看 RUB+CNY，VVIP 多看 USD；从每个品牌 tab 读取，自动按用户语言识别描述列
  - 数据来源：`services/outdoor_prices.py`，gspread Service Account 读私有 Sheet
- **描述翻译**：英文用户访问价格时，俄文描述自动经 DeepSeek 翻译并 Redis 缓存 30 天（`services/translation.py`）

### A-BF 俄罗斯服务中心（service_center.py）
- 设备检修查询：FSM 输入 CDEK 单号或 SN → 查 Sheet → 返回状态 + 订阅变更通知
- 状态变更由 `repair_monitor.py` 每 5 分钟轮询推送
- 管理员后台（密码触发）：SN 列表、跨品牌 SN 搜索

### A-BF 晨夜俱乐部（club.py）
- URL 按钮直跳，无 FSM

### Vandych VIP 隐藏菜单（vip.py）
- 获取折扣 / 支付空运 / 批发需求

## 库存同步公式（关键）

`inventory_sync.py` 每 5 分钟跑一次，公式：

```
QTYS = KYB 俄罗斯仓 tocUsableQty (可用数量) − JST 俄罗斯仓 order_lock (订单占有)
```

注意点：
- KYB 必须只统计**俄罗斯仓库**（默认 `RUS2`），不含东莞中转仓 SZW
- KYB 不同 SKU 的 `tocUsableQty` 行为不一致：有的已扣 JST 订单（如 TRS-335LRF），有的没扣（如 GEH50R）。所以要用 `tocUsableQty`，再减 JST `order_lock` 才能保证一致正确
- JST `get_stock_map` 必须**累加**多仓库的 `order_lock`，而不是覆盖
- 配置仓库过滤：
  - `KYB_RUSSIA_WAREHOUSE_CODES=RUS2`（默认）
  - `JST_RUSSIA_WAREHOUSE_CODE=...`（按聚水潭仓库编号填写）

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
- `analytics_events`：每个 Telegram update 一条（middlewares/analytics.py 写入），含 module / action / language / event_data
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

### 通用筛选
- 周期：今天 / 近 7 天 / 近 30 天 / 自定义起止日期
- 测试账号过滤：默认排除 `ADMIN_IDS` ∪ `ANALYTICS_TEST_USER_IDS` ∪ `users` 表中匹配 `ANALYTICS_TEST_USERNAMES` 的账号；勾"包含测试号"切回完整数据

### Excel 导出结构
每个导出 = **概览** sheet + **明细** sheet。明细列：
`时间 / TGID / 用户名 / 显示名称 / 等级 / 语言 / 模块 / 动作 / 结果`

### 用户分级
基于全时间窗口的 `hidden_access.password_success` 事件推导，等级优先级：
`vvip > svip > vip > vandych > service_admin > public`

## 密码 / Token / API Key 配置

| 变量 | 用途 |
|------|------|
| `VIP_INVENTORY_PASSWORD` | VIP 库存隐藏菜单 |
| `SVIP_INVENTORY_PASSWORD` | SVIP 库存 + 价格 |
| `VVIP_INVENTORY_PASSWORD` | VVIP 库存 + 价格（含美元） |
| `SERVICE_ADMIN_PASSWORD` | 服务中心管理后台 |
| `VANDYCH_PASSWORD` | Vandych VIP 菜单 |
| `JST_APP_KEY` / `JST_APP_SECRET` | 聚水潭应用密钥 |
| `JST_ACCESS_TOKEN` | 兜底 access_token（一般不用，自动获取失败时用） |
| `JST_IS_TEST` | 聚水潭测试环境（True 走 dev-api 域名） |
| `JST_RUSSIA_WAREHOUSE_CODE` | 聚水潭俄罗斯仓库编号（不填则汇总所有仓） |
| `KYB_APP_ID` / `KYB_APP_SECRET` / `KYB_TOKEN` | 跨运宝凭据 |
| `KYB_PLATFORM_CUSTOMER_CODE` | 跨运宝平台客户编码 |
| `KYB_RUSSIA_WAREHOUSE_CODES` | 跨运宝俄罗斯仓库编码列表（默认 `RUS2`） |
| `DEEPSEEK_API_KEY` | DeepSeek 翻译 |
| `DEEPSEEK_MODEL` | DeepSeek 模型（默认 `deepseek-v4-flash`） |
| `DEEPSEEK_API_URL` | DeepSeek chat-completions 端点 |
| `ANALYTICS_DASHBOARD_TOKEN` | Dashboard 访问 token（页面顶部输入） |
| `ANALYTICS_TEST_USERNAMES` | 测试账号 username 列表（不带 @） |
| `ANALYTICS_TEST_USER_IDS` | 测试账号 telegram_id 列表（数字） |
| `ADMIN_IDS` | 管理员 telegram_id 列表，也参与测试账号过滤 |

## Google Sheet 配置

### 连接方式
- **公开读** 走 CSV 导出（已弃用）
- **私有读写**：gspread + Service Account（`google_credentials.json`），所有 gspread 客户端都设置了 60s HTTP 超时

### 配置步骤
1. Google Cloud Console 创建 Service Account → 下载 JSON
2. 重命名为 `google_credentials.json` 放项目根目录
3. Service Account 邮箱加为 Sheet 编辑者
4. `.env` 填 Sheet ID：
   ```
   OUTDOOR_SHEET_ID=...
   SERVICE_CENTER_SHEET_ID=...
   DISCOUNT_SHEET_ID=...
   ```

### 列名/Tab 配置
| 用途 | 文件 | 关键常量 |
|------|------|---------|
| 户外库存（按 tier 多 tab） | `services/outdoor_sheets.py` | `COL_SKU` 等；tab 标题靠 `inventory_tiers.py` |
| 户外价格（每品牌一个 tab） | `services/outdoor_prices.py` | 列角色由 `_column_roles()` 自动识别 |
| 服务中心检修 | `services/service_center_sheet.py` | `COL_CDEK_IN`, `COL_SN`, ... |
| SN 跨品牌（同上 sheet 7 个 tab） | `services/sn_sheet.py` | `COL_SN`, `COL_NOTES` |
| 折扣 | `services/discount_sheet.py` | `COL_MODEL`, `COL_DISCOUNT`, ... |

### 价格表「描述」列识别规则
header 文本规则化后按如下顺序匹配语言：

```
含 "опис"          → ru
含 "描述"          → zh
含 "description"   → en
```

每行可同时存储 zh/en/ru 三个版本，未配置的语言通过 `description_for(lang)` 回退；英文用户在缺英文列时由 DeepSeek 自动翻译俄文。

## 关键约定

### Handler 组织
- 每模块一个文件 + 独立 `Router`
- 在 `app.py` 中通过 `dp.include_router()` 注册，顺序决定优先级
- 函数命名：`on_<动作>_<对象>`

### 隐藏入口（密码触发）
- 全部统一在 `handlers/hidden_entries.py` 处理，注册在 `start` 之后、其他功能 router 之前
- 验证通过后通过 `services/hidden_access.py` 在 FSM data 写 access token（TTL=10 分钟）
- 后续 callback 通过 `has_hidden_access(state, menu_key)` 验证权限

### CallbackData
- 使用 aiogram `CallbackData` 工厂类
- 前缀命名：`<模块>:<动作>`
- 全部定义在 `bot/keyboards/callbacks.py`

### FSM 状态管理
- 状态组定义在 `bot/states/`
- 存储用 Redis（`RedisStorage`）
- 流程结束必须 `state.clear()`

### 多语言 (i18n)
- 每个 handler 顶部 `TEXTS: dict[str, dict[str, str]]`
- 用 `_t(lang, key)` 取文本
- 语言回退链：用户 DB 偏好 → Telegram 客户端语言 → 默认 "zh"

### 数据库
- SQLAlchemy 2.0 async（`async_session`）
- 通过中间件注入 handler 的 `session` 参数
- **建表用 `Base.metadata.create_all()`**（在 `docker/entrypoint.sh` 里），不是 alembic
- 新增 model 必须在 `docker/entrypoint.sh` 加一行 import，否则 create_all 不会创建对应表

### 错误处理
- Handler 不要 try/except 吞异常
- 外部 API 调用包 try/except，记日志 + 友好提示
- Dispatcher 全局错误：`async def global_error_handler(event: ErrorEvent) -> bool`

## Docker 服务

| 服务 | 说明 |
|------|------|
| `bot` | 主应用（polling/webhook），entrypoint 跑 create_all |
| `mysql` | MySQL 8.0（仅内网） |
| `redis` | Redis 7（256MB LRU，AOF 持久化，仅内网） |
| `inventory-sync` | 每 5 分钟同步库存，外层 `timeout 240` 防卡死 |
| `repair-monitor` | 每 5 分钟轮询检修状态变更 |
| `analytics-dashboard` | aiohttp Web 服务（端口 8088） |

## 部署注意事项

- `.env` 中 `MYSQL_HOST=mysql`、`REDIS_HOST=redis`（Docker 服务名）
- `COMPOSE_PROJECT_NAME=abf-bot-v2`
- 代码更新必须 `docker compose up -d --build`，`restart` 不重建
- 新增 model 时**必须** rebuild `bot` 容器（entrypoint 跑 create_all 才会建新表），同时把 import 写进 `docker/entrypoint.sh`
- 数据库 `alembic_version` 表里有孤儿 revision（`38ba7ff1cb39`），不影响 create_all 路径，但执行 `alembic upgrade head` 会报多 head 错误。如需用 alembic：先 `DELETE FROM alembic_version;` 再 stamp 到最新

## 已知历史问题与修复

- 库存数量偏差：早期 `tocUsableQty - JST order_lock` 双重扣减；后期切到 `tocTotalQty` 又遇 KYB 不一致；最终方案是 `tocUsableQty - JST order_lock` 配合俄罗斯仓过滤
- 库存同步卡死 10 分钟：gspread 默认无 HTTP 超时，已加 60s 限制；Docker 层 `timeout 240` 保底
- 聚水潭 token 老过期：早期 refresh_token 用错 URL；改为 `getInitToken` + 随机 code 后稳定
- Dashboard 加载 500：新增 `analytics_annotations` 表后 entrypoint 没 import，create_all 跳过该表；已加 import
