# A-BF 跨境电商内部系统

A-BF 跨境电商团队的核心数字基础设施，包含对外 Telegram 客服 Bot 和对内企业微信 AI 助理两套系统。已在华为云 ECS 生产部署。

## 系统概述

### Telegram Bot（对外）
基于 aiogram 3.x 的多语言客服机器人，面向中俄跨境电商客户，支持中/英/俄三语。

- **莫斯科现货查询** — 公开/VIP/SVIP/VVIP 四级权限，密码触发隐藏菜单
- **价格查询** — 按品牌/SKU 查询 RUB/CNY/USD 报价，描述列自动多语言（DeepSeek 翻译俄→英）
- **A-BF 俄罗斯服务中心** — CDEK 单号/SN 序列号查询检修状态，状态变更自动推送通知
- **A-BF 晨夜俱乐部** — 直跳 TG 群链接
- **Vandych VIP 隐藏菜单** — 折扣码、空运支付、批发需求
- **用户埋点 Dashboard** — ECharts 看板（端口 8088），Excel 导出，活动节点标注

### 企业微信 AI 助理（对内）
基于 DeepSeek tool-calling 的内部 agent，自然语言对话，覆盖：

- 莫斯科库存/SKU 价格/Vandych 折扣查询
- Telegram Bot 日报与用户活跃排行
- SN 序列号验真、设备检修状态查询
- **速卖通折扣码一键创建**（多店铺，Cookie 管理后台 port 8089）

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Telegram Bot 框架 | aiogram 3.x |
| 企微 AI 助理 | WebSocket 长连接 + DeepSeek tool-calling |
| 数据库 | MySQL 8.0 + SQLAlchemy 2.0 (async) |
| 缓存 / FSM | Redis 7.x |
| Web 服务 | aiohttp（看板 + Cookie 管理后台） |
| 库存数据 | Google Sheets（gspread Service Account）|
| ERP 集成 | 聚水潭（JST）/ 跨运宝（KYB）|
| 速卖通集成 | MTOP 网页端 API（Cookie 鉴权）|
| 部署 | Docker Compose（7 个服务）|

## 快速开始

### 1. 克隆项目

```bash
git clone -b bot-v2 https://github.com/Neverlbc/Telegram-Bot.git A-BF-Telegram-Bot2
cd A-BF-Telegram-Bot2
```

### 2. 安装依赖

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入实际配置
```

### 4. 运行（开发模式）

```bash
python -m bot               # Telegram Bot（Polling）
python -m bot.wecom         # 企业微信 AI 助理
python -m bot.analytics_dashboard   # 埋点看板
python -m bot.ae_cookie_dashboard   # AE Cookie 管理后台
```

## 项目结构

```
bot/
├── __main__.py              # Telegram Bot 入口（Polling/Webhook）
├── config.py                # 所有配置（pydantic Settings）
├── app.py                   # Bot/Dispatcher/中间件/Router 注册
├── repair_monitor.py        # 独立脚本：检修状态轮询推送
├── sync.py                  # 独立脚本：手动触发库存同步
├── analytics_dashboard.py   # 用户埋点看板（aiohttp，端口 8088）
├── ae_cookie_dashboard.py   # 速卖通 Cookie 管理后台（aiohttp，端口 8089）
│
├── wecom/                   # 企业微信 AI 助理
│   ├── __main__.py          #   入口 + 消息路由 + 文件解析 + 并发控制
│   ├── client.py            #   WebSocket 客户端（连接/心跳/文件下载/回复）
│   ├── tools.py             #   9 个 LLM 工具函数
│   └── llm.py               #   DeepSeek tool-calling（最多 3 轮）
│
├── handlers/                # Telegram 消息处理器
├── keyboards/               # InlineKeyboard + CallbackData
├── middlewares/             # throttle / db / user / i18n / analytics
│
├── models/
│   ├── user.py
│   ├── analytics.py
│   ├── analytics_annotation.py
│   └── ae_store_cookie.py   # 速卖通店铺 Cookie + channel_id
│
└── services/
    ├── outdoor_sheets.py    # 户外库存（gspread + Redis）
    ├── outdoor_prices.py    # 价格表（多语言描述）
    ├── inventory_sync.py    # KYB tocUsableQty − JST order_lock
    ├── jushuitan.py         # 聚水潭 ERP（getInitToken 自动获取）
    ├── kuayunbao.py         # 跨运宝 WMS
    ├── aliexpress_mtop.py   # 速卖通 MTOP API（多店铺 Cookie）
    ├── service_center_sheet.py
    ├── sn_sheet.py
    ├── discount_sheet.py
    └── translation.py       # DeepSeek 俄→英翻译（Redis 缓存 30 天）
```

## Docker 服务

| 服务 | 端口 | 说明 |
|------|------|------|
| `bot` | — | Telegram Bot 主应用 |
| `redis` | — | Redis 7（仅内网）|
| `inventory-sync` | — | 每 5 分钟同步库存 |
| `repair-monitor` | — | 每 5 分钟轮询检修状态变更 |
| `analytics-dashboard` | 8088 | 用户埋点看板 |
| `ae-cookie-dashboard` | 8089 | 速卖通 Cookie 管理后台 |
| `wecom-agent` | — | 企业微信 AI 助理长连接 |

```bash
# 构建并启动所有服务
docker compose up -d --build

# 局部重建
docker compose up -d --build wecom-agent
docker compose up -d --build ae-cookie-dashboard

# 查看日志
docker compose logs -f bot
docker compose logs -f wecom-agent
```

## 关键环境变量

### 必填
| 变量 | 说明 |
|------|------|
| `BOT_TOKEN` | Telegram Bot Token |
| `MYSQL_PASSWORD` | MySQL 密码 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（翻译 + 企微 LLM）|

### 企业微信
| 变量 | 说明 |
|------|------|
| `WECOM_BOT_ID` | 企业微信智能机器人 BotID |
| `WECOM_BOT_SECRET` | 长连接 Secret |
| `WECOM_BOT_NAME` | 机器人显示名（默认 `A-BF跨境助理`）|

### 速卖通 Cookie 管理后台
| 变量 | 默认 | 说明 |
|------|------|------|
| `AE_COOKIE_DASHBOARD_PORT` | `8089` | 后台端口 |
| `AE_COOKIE_DASHBOARD_TOKEN` | — | 访问 token（空则无鉴权）|

### 库存同步
| 变量 | 说明 |
|------|------|
| `JST_APP_KEY` / `JST_APP_SECRET` | 聚水潭应用密钥 |
| `KYB_APP_ID` / `KYB_APP_SECRET` / `KYB_TOKEN` | 跨运宝凭据 |
| `KYB_RUSSIA_WAREHOUSE_CODES` | 默认 `RUS2` |

### Google Sheets
| 变量 | 说明 |
|------|------|
| `OUTDOOR_SHEET_ID` | 莫斯科户外现货 Sheet ID |
| `SERVICE_CENTER_SHEET_ID` | 服务中心检修 Sheet ID |
| `DISCOUNT_SHEET_ID` | VIP 折扣 Sheet ID |

完整配置说明见 `CLAUDE.md`。

## 数据库说明

项目使用 `Base.metadata.create_all()` 建表（在 `docker/entrypoint.sh`），不用 alembic 迁移。

**新增 model 时必须**：① 写 model 文件 ② 在 `docker/entrypoint.sh` 加 import ③ rebuild 容器。

新增列到已有表需在服务器手动执行 `ALTER TABLE`（create_all 不加列）。

## 速卖通折扣码功能

在企微 AI 助理中直接发消息创建折扣码：
> "帮我给 botterrun 创建一个满 200 减 1 的折扣码，有效期 1 天，发 10 张，每人限 1 张"

店铺 Cookie 通过 `http://服务器IP:8089` 管理后台配置，每个卖家账号的 `channel_id` 从速卖通促销页 URL `channelId=xxx` 获取。

也可在企微直接发命令更新 Cookie：
```
/update_cookie 店铺名 你的Cookie字符串
```
