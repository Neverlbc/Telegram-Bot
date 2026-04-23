# A-BF Telegram 客服 Bot（新版）

基于 aiogram 3.x 的多语言 Telegram 客服机器人，面向中俄跨境电商场景。支持中文、英文、俄语三语。

## 功能概述

- **莫斯科现货查询** — 公开查询（部分库存）/ VIP 查询（完整库存，密码保护），无货时一键联系客服或预约空运
- **A-BF 俄罗斯服务中心** — 服务说明、TG 入口跳转、设备检修进度查询（输入 CDEK 单号）、维修完成自动通知、管理员后台
- **A-BF 晨夜俱乐部** — 直接跳转俱乐部 TG 群链接
- **Vandych VIP 隐藏菜单** — 文本密码触发，含获取折扣码、空运支付链接、批发需求提交（≥5 件标记 VIP 优先人工）

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Bot 框架 | aiogram 3.x |
| 数据库 | MySQL 8.0 |
| 缓存 / FSM | Redis 7.x |
| ORM | SQLAlchemy 2.0 (async) |
| 数据库迁移 | Alembic |
| 库存数据 | Google Sheets（CSV 导出 + gspread 写回）|
| 部署 | Docker Compose |

## 快速开始

### 1. 克隆项目

```bash
git clone -b bot-v2 <repo-url>
cd "A-BF Telegram Bot2"
```

### 2. 安装依赖

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入实际配置（见下方变量说明）
```

### 4. 初始化数据库

```bash
alembic upgrade head
```

### 5. 运行

```bash
# 开发模式（Polling）
python -m bot

# 生产模式（Webhook）
python -m bot --webhook
```

## 项目结构

```
bot/
├── __main__.py              # 启动入口
├── config.py                # 配置加载（pydantic-settings，从 .env 读取）
├── app.py                   # Bot / Dispatcher / 中间件 / Router 注册
├── repair_monitor.py        # 独立脚本：轮询检修状态变更，推送通知
├── handlers/
│   ├── start.py             # /start、语言选择
│   ├── menu.py              # /menu、/cancel、主菜单、NavCallback 路由
│   ├── inventory.py         # 莫斯科现货查询（公开 / VIP）
│   ├── service_center.py    # 俄罗斯服务中心（检修查询 + 管理后台）
│   ├── club.py              # 晨夜俱乐部（URL 跳转）
│   ├── vip.py               # Vandych VIP 隐藏菜单
│   └── settings.py          # 用户设置、/lang、/help
├── keyboards/
│   ├── callbacks.py         # CallbackData 工厂（8 个类）
│   └── inline.py            # InlineKeyboard 构建器
├── middlewares/
│   ├── throttle.py          # 频率限制
│   ├── db.py                # DB 会话注入
│   ├── user.py              # 用户 upsert
│   └── i18n.py              # 语言注入
├── models/                  # SQLAlchemy ORM 实体
├── services/
│   ├── outdoor_sheets.py    # 户外库存 Google Sheet（读，Redis 缓存 5 分钟）
│   ├── service_center_sheet.py  # 服务中心检修表（查询 + watcher 注册）
│   ├── discount_sheet.py    # VIP 折扣表
│   ├── sheets_writer.py     # Google Sheets 写回（gspread）
│   ├── notification.py      # Bot 消息推送
│   └── inventory_sync.py    # 库存同步编排（JST + KYB → Sheets）
└── states/
    ├── inventory.py         # VIP 密码输入
    ├── service_center.py    # CDEK 单号输入 + 管理员密码
    └── vip.py               # 批发需求输入
```

## 环境变量说明

### 必填

| 变量 | 说明 |
|------|------|
| `BOT_TOKEN` | Telegram Bot Token |
| `MYSQL_PASSWORD` | MySQL 密码 |

### Google Sheets

| 变量 | 说明 |
|------|------|
| `GOOGLE_CREDENTIALS_FILE` | Service Account JSON 路径（默认 `google_credentials.json`）|
| `OUTDOOR_SHEET_ID` | 莫斯科户外现货 Sheet ID |
| `SERVICE_CENTER_SHEET_ID` | 服务中心检修 Sheet ID |
| `DISCOUNT_SHEET_ID` | VIP 折扣 Sheet ID |

### 密码入口

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VIP_INVENTORY_PASSWORD` | VIP 现货查询密码 | `ABFVIP2026` |
| `SERVICE_ADMIN_PASSWORD` | 服务中心管理员密码 | `service2026adminXXA` |
| `VANDYCH_PASSWORD` | Vandych VIP 菜单触发密码 | `ABFVandych2026XXA` |

### TG 链接

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CLUB_TG_LINK` | 晨夜俱乐部 TG 群链接 | `https://t.me/placeholder_club` |
| `SERVICE_CENTER_TG_LINK` | 服务中心 TG 入口链接 | `https://t.me/placeholder_service` |
| `HUMAN_AGENT_USERNAME` | 人工客服 TG 用户名（不带 @）| `ABFOfficialGroup` |
| `ALIEXPRESS_SHIPPING_URL` | Vandych VIP 空运支付链接 | — |

### 数据库 / 缓存 / 管理

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MYSQL_HOST` | `localhost` | |
| `MYSQL_PORT` | `3306` | |
| `MYSQL_USER` | `bot_user` | |
| `MYSQL_DATABASE` | `telegram_bot` | |
| `REDIS_HOST` | `localhost` | |
| `REDIS_PORT` | `6379` | |
| `ADMIN_IDS` | — | 管理员 TG ID，逗号分隔 |
| `SUPPORT_GROUP_ID` | `0` | 客服群组 TG ID |
| `WEBHOOK_URL` | — | 生产 Webhook 地址 |
| `WEBHOOK_PORT` | `8443` | |
| `LOG_LEVEL` | `INFO` | |

## 部署（Docker Compose）

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看日志
docker-compose logs -f bot
docker-compose logs -f repair-monitor

# 执行数据库迁移
docker-compose exec bot alembic upgrade head

# 停止服务
docker-compose down
```

### Docker 服务说明

| 服务 | 说明 |
|------|------|
| `bot` | 主应用 |
| `mysql` | MySQL 8.0 |
| `redis` | Redis 7（256MB LRU，AOF 持久化）|
| `inventory-sync` | 每 5 分钟同步库存（JST + KYB → Sheets）|
| `repair-monitor` | 每 5 分钟轮询检修状态变更，推送用户通知 |

## Google Sheet 列名配置

各 Sheet 的列名常量定义在对应 service 文件顶部（`COL_*`），可直接修改无需改业务逻辑：

| Sheet | 文件 |
|-------|------|
| 户外库存 | `bot/services/outdoor_sheets.py` |
| 服务中心检修 | `bot/services/service_center_sheet.py` |
| VIP 折扣 | `bot/services/discount_sheet.py` |

## 开发命令

```bash
pytest                                   # 全部测试
ruff check bot/ && ruff format bot/      # lint + 格式化
mypy bot/                                # 类型检查
alembic revision --autogenerate -m "描述"  # 新建迁移
```
