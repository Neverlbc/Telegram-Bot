# A-BF Telegram 客服 Bot（新版）

基于 aiogram 3.x 的多语言 Telegram 客服机器人，面向中俄跨境电商场景。支持中文、英文、俄语三语。已在华为云 ECS 部署运行。

## 功能概述

- **莫斯科现货查询** — 公开查询（部分库存）/ VIP 查询（完整库存，密码保护），无货时一键联系客服或预约空运
- **A-BF 俄罗斯服务中心** — 服务说明、TG 入口跳转、设备检修进度查询（输入 **CDEK 单号或 SN 序列号**）、状态感知底部提示（Done 显示回寄单号与维修报告、In Progress 显示延迟说明）、维修完成自动通知、管理员后台（文本密码触发，含 SN 跨品牌查询）
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
git clone -b bot-v2 https://github.com/Neverlbc/Telegram-Bot.git A-BF-Telegram-Bot2
cd A-BF-Telegram-Bot2
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
│   ├── service_center_sheet.py  # 服务中心检修表（CDEK/SN 查询 + watcher 注册）
│   ├── sn_sheet.py          # SN 跨品牌 tab 查询（7 个品牌，管理员搜索用）
│   ├── discount_sheet.py    # VIP 折扣表
│   ├── sheets_writer.py     # Google Sheets 写回（gspread）
│   ├── notification.py      # Bot 消息推送
│   └── inventory_sync.py    # 库存同步编排（JST + KYB → Sheets）
└── states/
    ├── inventory.py         # VIP 密码输入
    ├── service_center.py    # CDEK/SN 输入、管理员 SN 搜索
    └── vip.py               # 批发需求输入
```

## 环境变量说明

### 必填

| 变量 | 说明 |
|------|------|
| `BOT_TOKEN` | Telegram Bot Token |
| `MYSQL_PASSWORD` | MySQL 密码 |

### 数据库 / 缓存

| 变量 | Docker 部署值 | 说明 |
|------|-------------|------|
| `MYSQL_HOST` | `mysql` | Docker 服务名 |
| `MYSQL_PORT` | `3306` | |
| `MYSQL_USER` | `bot_user` | |
| `MYSQL_DATABASE` | 自定义 | |
| `REDIS_HOST` | `redis` | Docker 服务名 |
| `REDIS_PORT` | `6379` | |

### 密码入口

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VIP_INVENTORY_PASSWORD` | VIP 现货查询密码（按钮流程内输入）| `ABFVIP2026` |
| `SERVICE_ADMIN_PASSWORD` | 服务中心管理员密码（**直接发文本触发**）| `service2026adminXXA` |
| `VANDYCH_PASSWORD` | Vandych VIP 菜单触发密码（**直接发文本触发**）| `ABFVandych2026XXA` |

### TG 链接

| 变量 | 说明 |
|------|------|
| `CLUB_TG_LINK` | 晨夜俱乐部 TG 群链接 |
| `SERVICE_CENTER_TG_LINK` | 服务中心 TG 入口链接 |
| `HUMAN_AGENT_USERNAME` | 人工客服 TG 用户名（不带 @，默认 `ABFOfficialGroup`）|
| `ALIEXPRESS_SHIPPING_URL` | Vandych VIP 空运支付链接 |

### Google Sheets

| 变量 | 说明 |
|------|------|
| `GOOGLE_CREDENTIALS_FILE` | Service Account JSON 路径（默认 `google_credentials.json`）|
| `OUTDOOR_SHEET_ID` | 莫斯科户外现货 Sheet ID |
| `SERVICE_CENTER_SHEET_ID` | 服务中心检修 Sheet ID（同时用于 SN 跨品牌查询，各品牌 tab GID 硬编码在 `sn_sheet.py`）|
| `DISCOUNT_SHEET_ID` | VIP 折扣 Sheet ID |

### 其他

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `COMPOSE_PROJECT_NAME` | `abf-bot-v2` | 防止与其他实例容器名冲突 |
| `ADMIN_IDS` | — | 管理员 TG ID，逗号分隔 |
| `LOG_LEVEL` | `INFO` | |

## 部署（Docker Compose）

```bash
# 构建并启动所有服务
docker compose up -d --build

# 查看日志
docker compose logs -f bot
docker compose logs -f repair-monitor

# 首次部署：执行数据库迁移
sleep 15 && docker compose exec -T bot alembic upgrade head

# 若数据库有旧版 alembic_version 记录，先清理
docker compose exec -T mysql mysql -u bot_user -p'密码' 数据库名 -e "DELETE FROM alembic_version;"
docker compose exec -T bot alembic upgrade head
```

### Docker 服务说明

| 服务 | 说明 |
|------|------|
| `bot` | 主应用 |
| `mysql` | MySQL 8.0（仅内网）|
| `redis` | Redis 7（256MB LRU，AOF 持久化，仅内网）|
| `inventory-sync` | 每 5 分钟同步库存（JST + KYB → Sheets）|
| `repair-monitor` | 每 5 分钟轮询检修状态变更，推送用户通知 |

## Google Sheet 配置说明

1. 在 [Google Cloud Console](https://console.cloud.google.com) 创建 Service Account，下载 JSON 凭据
2. 将 JSON 文件重命名为 `google_credentials.json` 放到项目根目录
3. 在对应 Google Sheet 中把 Service Account 邮箱加为编辑者
4. 在 `.env` 中填写对应 Sheet ID（从 Sheet URL 中提取 `/d/` 后的部分）

各 Sheet 的列名常量在 service 文件顶部的 `COL_*` 变量中定义，可直接修改无需改业务逻辑。

## 开发命令

```bash
pytest                                   # 全部测试
ruff check bot/ && ruff format bot/      # lint + 格式化
mypy bot/                                # 类型检查
alembic revision --autogenerate -m "描述"  # 新建迁移
```
