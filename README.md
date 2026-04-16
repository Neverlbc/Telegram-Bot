# Telegram 跨境电商客服 Bot

基于 aiogram 3.x 的多语言 Telegram 客服机器人，面向中俄跨境电商场景，支持商品目录浏览、售中下单、售后支持、物流查询和智能客服。

## 功能概述

- **多语言支持** — 中文、英文、俄语自动识别与切换
- **售前咨询** — 查看商品清单（自动回复预设报价/规格）、配送说明、常见问题
- **售中下单** — 批发订单提交（留言数量型号 → 转人工处理）
- **售后支持** — 包含三个子模块：
  - 订单状态查询：对接聚水潭 ERP，已发货/未发货智能分流，未发货调用 LLM 自动回复，触发 5 次转特定人工
  - 物流查询：支持莫斯科发货（CDEK、RU Post、Cainiao、空运）和中国发货，输入跟踪号自动查询
  - 设备支持：序列号查询（归属公司）、设备问题报修（固件/硬件/软件/远程）、更多选项
- **客服合作** — 商务合作、批发咨询、转接人工客服

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.11+ |
| Bot 框架 | aiogram | 3.x |
| 数据库 | MySQL | 8.0 |
| 缓存/状态 | Redis | 7.x |
| ORM | SQLAlchemy | 2.0 (async) |
| DB 驱动 | aiomysql | — |
| 数据库迁移 | Alembic | — |
| ERP 对接 | 聚水潭 API | — |
| 物流查询 | CDEK / RU Post / Cainiao API | — |
| 部署 | Docker Compose | — |
| 服务器 | 华为云 ECS | — |

## 环境要求

- Python 3.11+
- MySQL 8.0+
- Redis 7.x+
- Docker & Docker Compose（生产部署）
- 聚水潭 ERP 账号（售后订单查询）

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url>
cd telegram-bot
```

### 2. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入实际配置
```

### 4. 初始化数据库

```bash
# 执行数据库迁移
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
telegram-bot/
├── bot/
│   ├── __main__.py              # 启动入口
│   ├── config.py                # 配置加载（从 .env 读取）
│   ├── app.py                   # 应用初始化（Bot、Dispatcher、中间件注册）
│   ├── middlewares/
│   │   ├── i18n.py              # 多语言中间件
│   │   ├── db.py                # 数据库会话注入
│   │   └── throttle.py          # 频率限制
│   ├── handlers/
│   │   ├── start.py             # /start 命令、语言选择
│   │   ├── menu.py              # 主菜单导航
│   │   ├── presale.py           # 售前咨询（商品清单/配送说明/常见问题）
│   │   ├── order.py             # 售中下单（批发询价）
│   │   ├── aftersale.py         # 售后支持（订单状态查询）
│   │   ├── logistics.py         # 物流查询
│   │   ├── device.py            # 设备支持（配置序列号/设备问题/更多选项）
│   │   ├── support.py           # 客服与商务合作
│   │   └── settings.py          # 用户设置
│   ├── keyboards/
│   │   ├── inline.py            # InlineKeyboard 构建器
│   │   └── callbacks.py         # CallbackData 定义
│   ├── services/
│   │   ├── jushuitan.py         # 聚水潭 ERP 对接
│   │   ├── logistics_tracker.py # 物流查询服务（CDEK/RU Post/Cainiao）
│   │   ├── ai_reply.py          # AI 自动回复服务
│   │   └── notification.py      # 通知服务
│   ├── models/
│   │   ├── base.py              # SQLAlchemy Base
│   │   ├── user.py              # 用户模型
│   │   ├── product.py           # 商品 & 分类模型
│   │   ├── order.py             # 订单模型
│   │   └── ticket.py            # 客服工单模型
│   ├── states/
│   │   ├── order.py             # 下单 FSM 状态组
│   │   └── logistics.py         # 物流查询 FSM 状态组
│   └── locales/
│       ├── zh/                  # 中文翻译
│       ├── en/                  # 英文翻译
│       └── ru/                  # 俄语翻译
├── alembic/                     # 数据库迁移脚本
│   └── versions/
├── tests/                       # 测试
├── docker-compose.yml           # 容器编排
├── Dockerfile                   # Bot 镜像
├── .env.example                 # 环境变量模板
├── requirements.txt             # Python 依赖
├── alembic.ini                  # Alembic 配置
├── pyproject.toml               # 项目元数据
└── CLAUDE.md                    # Claude Code 开发指引
```

## 环境变量说明

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `BOT_TOKEN` | Telegram Bot Token | `123456:ABC-DEF...` |
| `MYSQL_HOST` | MySQL 主机地址 | `localhost` |
| `MYSQL_PORT` | MySQL 端口 | `3306` |
| `MYSQL_USER` | MySQL 用户名 | `bot_user` |
| `MYSQL_PASSWORD` | MySQL 密码 | — |
| `MYSQL_DATABASE` | 数据库名 | `telegram_bot` |
| `REDIS_HOST` | Redis 主机地址 | `localhost` |
| `REDIS_PORT` | Redis 端口 | `6379` |
| `REDIS_PASSWORD` | Redis 密码（可选） | — |
| `JUSHUITAN_APP_KEY` | 聚水潭应用 Key | — |
| `JUSHUITAN_APP_SECRET` | 聚水潭应用 Secret | — |
| `CDEK_CLIENT_ID` | CDEK API 客户端 ID | — |
| `CDEK_CLIENT_SECRET` | CDEK API 客户端 Secret | — |
| `WEBHOOK_URL` | Webhook 地址（生产环境） | `https://bot.example.com/webhook` |
| `WEBHOOK_PORT` | Webhook 监听端口 | `8443` |
| `ADMIN_IDS` | 管理员 Telegram ID 列表 | `123456,789012` |
| `SUPPORT_GROUP_ID` | 客服群组 Telegram ID | `-1001234567890` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

## 部署（华为云 Docker Compose）

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看日志
docker-compose logs -f bot

# 执行数据库迁移
docker-compose exec bot alembic upgrade head

# 停止服务
docker-compose down
```

## 开发命令

```bash
# 运行测试
pytest

# 运行单个测试
pytest tests/test_logistics.py -v

# 代码检查
ruff check bot/

# 代码格式化
ruff format bot/

# 创建数据库迁移
alembic revision --autogenerate -m "描述"

# 类型检查
mypy bot/
```
