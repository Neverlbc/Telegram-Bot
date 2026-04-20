# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

Telegram 跨境电商客服 Bot — 基于 aiogram 3.x，面向中俄跨境电商场景。核心功能：商品目录、售中下单（批发）、售后支持（对接聚水潭 ERP）、物流查询（CDEK/RU Post/Cainiao）、AI 智能回复、人工客服转接。支持中/英/俄三语。

## 常用命令

```bash
# 启动（开发模式，Polling）
python -m bot

# 启动（生产模式，Webhook）
python -m bot --webhook

# 测试
pytest                                 # 全部测试
pytest tests/test_logistics.py -v      # 单个文件
pytest -k "test_aftersale" -v          # 按名称匹配

# 代码质量
ruff check bot/                        # lint
ruff format bot/                       # 格式化
mypy bot/                              # 类型检查

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head
alembic downgrade -1

# Docker
docker-compose up -d --build
docker-compose logs -f bot
```

## 架构概览

```
bot/
├── __main__.py          # 入口，解析参数决定 Polling/Webhook
├── config.py            # pydantic Settings 从 .env 加载配置
├── app.py               # 创建 Bot、Dispatcher，注册中间件和路由
├── handlers/            # 按功能拆分的 aiogram Router
│   ├── start.py         #   /start、语言选择
│   ├── menu.py          #   主菜单导航
│   ├── presale.py       #   售前咨询（商品清单/配送说明/常见问题/自动回复）
│   ├── order.py         #   售中下单（批发询价 → 转人工）
│   ├── aftersale.py     #   售后支持入口 + 订单状态查询（聚水潭）
│   ├── logistics.py     #   售后支持 → 物流查询（CDEK/RU Post/Cainiao/空运）
│   ├── device.py        #   售后支持 → 设备支持（序列号查询/设备问题/更多选项）
│   ├── support.py       #   客服合作、转人工
│   └── settings.py      #   用户设置
├── keyboards/           # InlineKeyboard 构建 + CallbackData 工厂
├── middlewares/          # i18n、DB 会话注入、频率限制
├── models/              # SQLAlchemy 2.0 async 模型
├── services/            # 业务逻辑（聚水潭、物流查询、AI 回复、通知）
├── states/              # aiogram FSM StatesGroup 定义
└── locales/             # GNU gettext 翻译文件 (zh/en/ru)
```

**请求处理链路：** Telegram → aiogram Dispatcher → 中间件链（throttle → db → i18n） → Router → Handler → Service → 外部 API（聚水潭/物流）/ Model/DB

## 关键约定

### Handler 组织
- 每个功能模块一个文件，内部创建独立 `Router`
- 在 `app.py` 中通过 `dp.include_router()` 注册
- Handler 函数命名：`on_<动作>_<对象>`，如 `on_query_logistics`、`on_select_category`

### CallbackData
- 使用 aiogram `CallbackData` 工厂类，不要手拼字符串
- 前缀命名：`<模块>:<动作>`，如 `catalog:select`、`logistics:track`、`support:human`

### FSM 状态管理
- 状态组定义在 `bot/states/` 下，每个流程一个文件
- 状态存储使用 Redis（`RedisStorage`）
- 流程结束必须调用 `state.clear()` 清理状态

### 多语言 (i18n)
- 翻译文件在 `bot/locales/{zh,en,ru}/LC_MESSAGES/`
- 所有面向用户的文本必须通过 `_()` 函数获取，禁止硬编码
- 新增文本后执行翻译文件更新

### 外部 API 对接
- 聚水潭 ERP：封装在 `bot/services/jushuitan.py`，订单状态查询需要授权
- 物流查询：封装在 `bot/services/logistics_tracker.py`，策略模式适配多家物流商
- 所有外部 API 调用必须有超时设置和异常处理
- API 密钥通过环境变量注入，不硬编码

### 数据库
- 使用 SQLAlchemy 2.0 async 风格（`async_session`）
- 会话通过中间件注入到 handler 的 `session` 参数
- 模型放在 `bot/models/`，一个文件一个领域实体
- 迁移通过 Alembic 管理，禁止手动改表

### AI 自动回复
- 未发货订单由 AI 生成拖延回复
- 同一用户对同一订单触发 5 次后自动转特定人工
- 触发计数存储在 Redis，key 格式：`ai_reply:{user_id}:{order_id}`

### 错误处理
- Handler 层不要 try/except 吞掉异常
- 在 Dispatcher 层通过 `error_handler` 统一处理
- 外部 API 调用异常需记录日志并给用户友好提示
