# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Telegram 跨境电商客服 Bot — 基于 aiogram 3.x，面向中俄跨境电商场景（**新版架构**）。
核心功能：莫斯科现货查询（公开/VIP 两级）、俄罗斯服务中心（设备检修追踪）、晨夜俱乐部、Vandych VIP 隐藏菜单。支持中/英/俄三语。

## 常用命令

```bash
# 启动（开发模式，Polling）
python -m bot

# 启动（生产模式，Webhook）
python -m bot --webhook

# 测试
pytest                          # 全部测试
pytest tests/test_callbacks.py -v
pytest tests/test_config.py -v

# 代码质量
ruff check bot/                 # lint
ruff format bot/                # 格式化
mypy bot/                       # 类型检查

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head
alembic downgrade -1

# Docker
docker-compose up -d --build
docker-compose logs -f bot
docker-compose logs -f repair-monitor
```

## 架构概览

```
bot/
├── __main__.py              # 入口，解析参数决定 Polling/Webhook
├── config.py                # pydantic Settings，从 .env 加载配置
├── app.py                   # Bot、Dispatcher、中间件、路由注册
├── repair_monitor.py        # 独立脚本：轮询检修状态变更并推送通知
├── handlers/                # aiogram Router，按功能拆分
│   ├── start.py             #   /start、语言选择
│   ├── menu.py              #   /menu、/cancel、主菜单、NavCallback 路由
│   ├── inventory.py         #   莫斯科现货查询（公开/VIP 两级）
│   ├── service_center.py    #   A-BF 俄罗斯服务中心（检修查询 + 管理后台）
│   ├── club.py              #   A-BF 晨夜俱乐部（URL 跳转）
│   ├── vip.py               #   Vandych VIP 隐藏菜单（折扣/空运/批发）
│   └── settings.py          #   用户设置、/lang、/help
├── keyboards/
│   ├── callbacks.py         # CallbackData 工厂（8 个类）
│   └── inline.py            # InlineKeyboard 构建器（15+ 个函数）
├── middlewares/
│   ├── throttle.py          # 频率限制（Redis）
│   ├── db.py                # DB 会话注入
│   ├── user.py              # 用户 upsert
│   └── i18n.py              # 语言注入（lang 参数）
├── models/                  # SQLAlchemy 2.0 async ORM 实体
├── services/
│   ├── outdoor_sheets.py    # 莫斯科户外库存（Google Sheets，Redis 缓存）
│   ├── service_center_sheet.py  # 服务中心检修表（查询 + watcher 注册）
│   ├── discount_sheet.py    # VIP 折扣表（Google Sheets）
│   ├── sheets_writer.py     # Google Sheets 写回（gspread）
│   ├── notification.py      # 推送通知（群组/单个客服）
│   └── inventory_sync.py    # 库存同步编排（JST + KYB → Sheets）
├── states/
│   ├── inventory.py         # InventoryStates（VIP 密码输入）
│   ├── service_center.py    # ServiceCenterStates（CDEK 输入 + 管理员密码）
│   └── vip.py               # VipStates（批发需求输入）
└── locales/                 # 占位符（多语言用硬编码字典实现，未使用 gettext）
```

**请求处理链路：** Telegram → Dispatcher → 中间件链（throttle → db → user → i18n）→ Router → Handler → Service → Google Sheets / Redis / 通知

**Router 注册顺序（app.py）：**
`start → menu → inventory → service_center → club → settings → vip`
（vip 最后注册，避免文本输入捕获 FSM 中的密码/型号输入）

## 菜单结构

```
公开主菜单（3 按钮）
├── 🔍 莫斯科现货查询     → inventory.py
├── 🛠 A-BF 俄罗斯服务中心 → service_center.py
└── 🌙 A-BF 晨夜俱乐部    → URL 按钮（club_tg_link）

隐藏入口（文本触发）
└── 发送 VANDYCH_PASSWORD  → vip.py（Vandych 隐藏菜单）
```

## 功能模块说明

### 莫斯科现货查询（inventory.py）
- **公开查询**：读 Outdoor Sheet，仅展示 `is_public=True` 行
- **VIP 查询**：FSM 输入密码（`vip_inventory_password`）→ 读完整 Outdoor Sheet
- 无货时公开查询联系客服（带 TGID 标签），VIP 无货标记空运需求
- 数据来源：`services/outdoor_sheets.py`，Redis 缓存 5 分钟

### A-BF 俄罗斯服务中心（service_center.py）
- **服务说明**：静态文本
- **TG 入口链接**：跳转 `service_center_tg_link`
- **设备检修查询**：FSM 输入 CDEK 单号 → 查 Google Sheet → 返回状态 + 订阅变更通知
- **管理员入口**：密码（`service_admin_password`）→ 后台菜单（通知说明 + SN 列表）
- 状态变更由 `repair_monitor.py` 每 5 分钟轮询推送

### A-BF 晨夜俱乐部（club.py）
- 直接返回 URL 按钮，跳转 `club_tg_link`，无 FSM

### Vandych VIP 隐藏菜单（vip.py）
- 文本触发：用户发送 `VANDYCH_PASSWORD` 后展示隐藏菜单
- **获取折扣**：读折扣 Sheet → 返回链接 + 折扣码（仅本次有效提示）
- **支付空运**：发送 `aliexpress_shipping_url` + 折扣码
- **批发需求**：FSM 输入「型号 数量」→ ≥5 件标记 VIP 优先人工，否则普通批发

## 密码入口配置

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `VIP_INVENTORY_PASSWORD` | VIP 现货查询密码 | `ABFVIP2026` |
| `SERVICE_ADMIN_PASSWORD` | 服务中心管理员密码 | `service2026adminXXA` |
| `VANDYCH_PASSWORD` | Vandych VIP 菜单触发密码 | `ABFVandych2026XXA` |

## Google Sheet 列名配置

列名常量定义在对应 service 文件顶部，可直接修改：

| Sheet | Service 文件 | 关键列常量 |
|-------|-------------|-----------|
| 户外库存 Sheet (`outdoor_sheet_id`) | `services/outdoor_sheets.py` | `COL_SKU`, `COL_NAME`, `COL_QTY`, `COL_PUBLIC`, `COL_NOTES` |
| 服务中心 Sheet (`service_center_sheet_id`) | `services/service_center_sheet.py` | `COL_CDEK_IN`, `COL_SN`, `COL_MODEL`, `COL_STATUS`, `COL_TGID`, `COL_CDEK_OUT` |
| 折扣 Sheet (`discount_sheet_id`) | `services/discount_sheet.py` | `COL_MODEL`, `COL_DISCOUNT`, `COL_LINK`, `COL_CODE`, `COL_ACTIVE` |

## 关键约定

### Handler 组织
- 每个功能模块一个文件，内部创建独立 `Router`
- 在 `app.py` 中通过 `dp.include_router()` 注册，顺序决定优先级
- Handler 函数命名：`on_<动作>_<对象>`，如 `on_cdek_no_input`、`on_vip_password_input`
- 供其他模块调用的工具函数（如 `show_sc_menu`）定义在文件末尾

### CallbackData
- 使用 aiogram `CallbackData` 工厂类，不要手拼字符串
- 前缀命名：`<模块>:<动作>`，如 `inv:category`、`sc:repair`、`vip:discount`
- 所有 callback 类定义在 `bot/keyboards/callbacks.py`

### FSM 状态管理
- 状态组定义在 `bot/states/` 下，每个流程一个文件
- 状态存储使用 Redis（`RedisStorage`）
- 流程结束必须调用 `state.clear()` 清理
- `/menu` 和 `/cancel` 命令在进入前都清理状态

### 多语言 (i18n)
- 每个 handler 文件顶部定义 `TEXTS: dict[str, dict[str, str]]`（zh/en/ru）
- 通过辅助函数 `_t(lang, key)` 获取文本，禁止硬编码面向用户的字符串
- i18n middleware 向所有 handler 注入 `lang: str` 参数（"zh"/"en"/"ru"）
- 语言回退链：用户 DB 偏好 → Telegram 客户端语言 → 默认 "zh"

### Google Sheets 访问
- **只读（公开 Sheet）**：CSV 导出 URL，无需认证，Redis 缓存 5 分钟
- **读写（私有 Sheet）**：gspread + Service Account（`google_credentials.json`）
- Sheet ID 通过环境变量注入（`outdoor_sheet_id`、`service_center_sheet_id`、`discount_sheet_id`）
- 所有 Sheet 访问需有超时设置和异常处理

### 人工转接
- 统一跳转 `@{human_agent_username}`（默认 `ABFOfficialGroup`）
- URL 格式：`https://t.me/{username}?text={prefill}`，预填消息含 TGID 标签

### 错误处理
- Handler 层不要 try/except 吞掉异常
- 外部 API（Google Sheets）调用包裹 try/except，记录日志并给用户友好提示
- Dispatcher 层通过 `error_handler` 统一处理未捕获异常

### 数据库
- 使用 SQLAlchemy 2.0 async 风格（`async_session`）
- 会话通过中间件注入到 handler 的 `session` 参数
- 迁移通过 Alembic 管理，禁止手动改表

## Docker 服务

| 服务 | 说明 |
|------|------|
| `bot` | 主应用（polling/webhook）|
| `mysql` | MySQL 8.0，port 3306 |
| `redis` | Redis，port 6379，256MB LRU，AOF 持久化 |
| `inventory-sync` | 每 5 分钟：JST + KYB → 写回 Sheets → 清缓存 |
| `repair-monitor` | 每 5 分钟：轮询检修状态变更 → 推送用户通知 |
