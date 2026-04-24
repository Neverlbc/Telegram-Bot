# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Telegram 跨境电商客服 Bot — 基于 aiogram 3.x，面向中俄跨境电商场景（**新版架构，已部署运行**）。
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

# Docker（服务器）
docker compose up -d --build    # 构建并启动
docker compose logs -f bot      # 查看 bot 日志
docker compose logs -f repair-monitor
docker compose restart bot      # 仅重启（不重建镜像）
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
│   ├── club.py              #   A-BF 晨夜俱乐部（URL 跳转，无 router callbacks）
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
│   ├── service_center_sheet.py  # 服务中心检修表（CDEK/SN 查询 + watcher 注册）
│   ├── sn_sheet.py          # SN 序列号跨品牌 tab 查询（7 个品牌，管理员 SN 搜索用）
│   ├── discount_sheet.py    # VIP 折扣表（Google Sheets）
│   ├── sheets_writer.py     # Google Sheets 写回（gspread）
│   ├── notification.py      # 推送通知（群组/单个客服）
│   └── inventory_sync.py    # 库存同步编排（JST + KYB → Sheets）
├── states/
│   ├── inventory.py         # InventoryStates（VIP 密码输入）
│   ├── service_center.py    # ServiceCenterStates（CDEK 单号输入）
│   └── vip.py               # VipStates（批发需求输入）
└── locales/                 # 占位符（多语言用硬编码字典实现，未使用 gettext）
```

**请求处理链路：** Telegram → Dispatcher → 中间件链（throttle → db → user → i18n）→ Router → Handler → Service → Google Sheets / Redis / 通知

**Router 注册顺序（app.py）：**
`start → menu → inventory → service_center → settings → vip`
（vip 最后注册，避免文本输入捕获 FSM 中的密码/型号输入）

## 菜单结构

```
公开主菜单（4 按钮）
├── 🔍 莫斯科现货查询        → inventory.py
├── 🛠 A-BF 俄罗斯服务中心   → service_center.py
├── 🌙 A-BF 昼夜俱乐部       → URL 按钮（club_tg_link）
└── ⚙️ 设置                  → 语言切换面板（个人中心已隐藏）

隐藏入口（文本触发，无按钮）
├── 发送 SERVICE_ADMIN_PASSWORD → service_center.py 管理后台
└── 发送 VANDYCH_PASSWORD       → vip.py（Vandych 隐藏菜单）
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
- **设备检修查询**：FSM 输入 CDEK 单号 **或 SN 序列号** → 查 Google Sheet → 返回状态
  - 状态底部说明按状态分三种：
    - `Done`：📦 设备已寄回 + 回寄 CDEK 单号 + 维修报告摘要
    - `In Progress`：延迟说明文案（三语），建议直联服务中心频道
    - 其他：✅ 已订阅状态更新通知
  - 查询结果自动注册 watcher，状态变更时由 `repair_monitor.py` 每 5 分钟轮询推送
- **管理员入口**：直接发送 `service_admin_password` 文本（无按钮）→ 后台菜单
  - SN 列表：展示全部检修记录（最多 30 条）
  - SN 搜索：精确匹配序列号，调用 `services/sn_sheet.py` 跨品牌 tab 查询
    - 找到：三语确认文案（"已在数据库中找到，由我公司提供"）
    - 未找到：三语说明（"无法确认是否购自我司，请联系销售经理"）

### A-BF 晨夜俱乐部（club.py）
- 主菜单直接展示 URL 按钮，跳转 `club_tg_link`，无 FSM，无 router callbacks

### Vandych VIP 隐藏菜单（vip.py）
- 文本触发：用户发送 `VANDYCH_PASSWORD` 后展示隐藏菜单
- **获取折扣**：读折扣 Sheet → 返回链接 + 折扣码（仅本次有效提示）
- **支付空运**：发送 `aliexpress_shipping_url` + 折扣码
- **批发需求**：FSM 输入「型号 数量」→ ≥5 件标记 VIP 优先人工，否则普通批发

## 密码入口配置

| 变量 | 用途 | 触发方式 | 默认值 |
|------|------|---------|--------|
| `VIP_INVENTORY_PASSWORD` | VIP 现货查询 | 按钮流程内输入 | `ABFVIP2026` |
| `SERVICE_ADMIN_PASSWORD` | 服务中心管理后台 | **直接发文本**（无按钮） | `service2026adminXXA` |
| `VANDYCH_PASSWORD` | Vandych VIP 菜单 | **直接发文本**（无按钮） | `ABFVandych2026XXA` |

## Google Sheet 配置

### 连接方式
- **只读公开 Sheet**（户外库存）：CSV 导出 URL，无需认证，Redis 缓存 5 分钟
- **读写私有 Sheet**（服务中心、折扣）：gspread + Service Account（`google_credentials.json`）

### 配置步骤
1. 在 Google Cloud Console 创建 Service Account，下载 JSON 凭据
2. 将 JSON 文件重命名为 `google_credentials.json` 放到项目根目录
3. 在 Google Sheet 中把该 Service Account 的邮箱加为编辑者
4. 在 `.env` 中填写 Sheet ID（从 Sheet URL 中提取）：
   ```
   OUTDOOR_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
   SERVICE_CENTER_SHEET_ID=你的服务中心SheetID
   DISCOUNT_SHEET_ID=你的折扣SheetID
   ```

### 列名配置
列名常量定义在对应 service 文件顶部，可直接修改：

| Sheet | Service 文件 | 关键列常量 |
|-------|-------------|-----------|
| 户外库存 (`outdoor_sheet_id`) | `services/outdoor_sheets.py` | `COL_SKU`, `COL_NAME`, `COL_QTY`, `COL_PUBLIC`, `COL_NOTES` |
| 服务中心检修 (`service_center_sheet_id`, GID=1205973697) | `services/service_center_sheet.py` | `COL_CDEK_IN`, `COL_SN`, `COL_MODEL`, `COL_STATUS`, `COL_CDEK_OUT`, `COL_SUMMARY` |
| SN 品牌表（同 `service_center_sheet_id`，7个tab GID 硬编码） | `services/sn_sheet.py` | `COL_SN`, `COL_NOTES`；A列=型号，各品牌列名不同 |
| 折扣 (`discount_sheet_id`) | `services/discount_sheet.py` | `COL_MODEL`, `COL_DISCOUNT`, `COL_LINK`, `COL_CODE`, `COL_ACTIVE` |

## 关键约定

### Handler 组织
- 每个功能模块一个文件，内部创建独立 `Router`
- 在 `app.py` 中通过 `dp.include_router()` 注册，顺序决定优先级
- Handler 函数命名：`on_<动作>_<对象>`，如 `on_cdek_no_input`、`on_admin_password`
- 供其他模块调用的工具函数（如 `show_sc_menu`）定义在文件末尾

### 隐藏入口（文本密码触发）
- 用 `@router.message(StateFilter(default_state), F.text == settings.xxx_password)` 捕获
- 必须加 `StateFilter(default_state)` 避免在 FSM 流程中误触发
- 不在任何菜单里显示按钮

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

### 错误处理
- Handler 层不要 try/except 吞掉异常
- 外部 API（Google Sheets）调用包裹 try/except，记录日志并给用户友好提示
- Dispatcher 全局错误处理：`async def global_error_handler(event: ErrorEvent) -> bool`

### 数据库
- 使用 SQLAlchemy 2.0 async 风格（`async_session`）
- 会话通过中间件注入到 handler 的 `session` 参数
- 迁移通过 Alembic 管理，禁止手动改表
- 容器启动时自动执行 `alembic upgrade head`（docker/entrypoint.sh）

## Docker 服务

| 服务 | 说明 |
|------|------|
| `bot` | 主应用（polling/webhook）|
| `mysql` | MySQL 8.0（仅内网，不暴露端口）|
| `redis` | Redis 7（256MB LRU，AOF 持久化，仅内网）|
| `inventory-sync` | 每 5 分钟同步库存（JST + KYB → Sheets）|
| `repair-monitor` | 每 5 分钟轮询检修状态变更 → 推送用户通知 |

## 部署注意事项

- `.env` 中 `MYSQL_HOST=mysql`、`REDIS_HOST=redis`（Docker 服务名，非 localhost）
- `COMPOSE_PROJECT_NAME=abf-bot-v2`（避免与其他 bot 实例容器名冲突）
- 代码更新后必须 `docker compose up -d --build` 重建镜像，`restart` 不重建
- 首次部署或数据库有旧版 alembic_version 时，需手动清理：
  ```bash
  docker compose exec -T mysql mysql -u bot_user -p'密码' 数据库名 -e "DELETE FROM alembic_version;"
  docker compose exec -T bot alembic upgrade head
  ```
