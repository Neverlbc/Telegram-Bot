# 项目计划（按功能模块）

## 模块总览

| 模块 | 名称 | 依赖模块 | 优先级 |
|------|------|---------|--------|
| M1 | 项目基础搭建 | — | P0 |
| M2 | 用户系统 | M1 | P0 |
| M3 | 售前咨询（商品清单/配送说明/FAQ/自动回复） | M1, M2 | P0 |
| M4 | 售中下单（批发询价） | M1, M2 | P0 |
| M5 | 售后支持（含3个子模块） | M1, M2 | P0 |
| M5a | └─ 订单状态查询（聚水潭对接 + LLM自动回复） | M5 | P0 |
| M5b | └─ 物流查询（CDEK/RU Post/Cainiao/空运） | M5 | P0 |
| M5c | └─ 设备支持（序列号查询/设备问题/更多选项） | M5 | P1 |
| M6 | 客服系统（转人工） | M2 | P1 |
| M7 | 国际化完善 | M2~M6 | P1 |
| M8 | 部署与运维 | 全部 | P2 |

**建议开发顺序：** M1 → M2 → M3 → M4 → M5 → M5a → M5b → M5c → M6 → M7 → M8

---

## M1：项目基础搭建

**目标：** 搭建项目骨架，配通数据库和 Redis 连接，Bot 能启动并响应基础命令。

| # | 任务 | 产出 |
|---|------|------|
| 1.1 | 初始化项目结构（目录、pyproject.toml、requirements.txt） | 完整目录骨架 |
| 1.2 | 配置管理（pydantic Settings + .env） | `bot/config.py`、`.env.example` |
| 1.3 | SQLAlchemy 2.0 async 配置 + aiomysql 连接池 | `bot/models/base.py` |
| 1.4 | Alembic 初始化与迁移配置 | `alembic/`、`alembic.ini` |
| 1.5 | Redis 连接配置（RedisStorage for FSM） | Redis 连接工具 |
| 1.6 | aiogram Bot + Dispatcher 初始化 | `bot/app.py`、`bot/__main__.py` |
| 1.7 | 中间件框架（DB 会话注入、频率限制） | `bot/middlewares/` |
| 1.8 | 全局错误处理器（Dispatcher 层） | 错误处理模块 |
| 1.9 | Docker Compose 编排（Bot + MySQL + Redis） | `Dockerfile`、`docker-compose.yml` |
| 1.10 | 代码质量工具配置（ruff、mypy、pytest） | `pyproject.toml` 配置 |

**验收标准：**
- `python -m bot` 能启动，Bot 在 Telegram 中在线
- 数据库连接正常，Alembic 迁移可执行
- Redis 连接正常
- `docker-compose up` 一键启动所有服务

---

## M2：用户系统

**目标：** 新用户启动 Bot 时完成语言选择和注册，老用户直接进入主菜单。

| # | 任务 | 产出 |
|---|------|------|
| 2.1 | users 表模型 + 迁移 | `bot/models/user.py` |
| 2.2 | /start 命令 — 新用户欢迎语（中英俄同时展示） | `bot/handlers/start.py` |
| 2.3 | 语言选择 InlineKeyboard（中文/English/Русский） | `bot/keyboards/` |
| 2.4 | 语言选择回调处理 — 保存到 DB | handler + service |
| 2.5 | /start 老用户识别 — 直接进入主菜单 | handler 逻辑 |
| 2.6 | 主菜单 InlineKeyboard（7 个功能入口） | `bot/handlers/menu.py` |
| 2.7 | i18n 中间件 — 根据用户语言注入翻译函数 | `bot/middlewares/i18n.py` |
| 2.8 | 中/英/俄基础翻译文件（欢迎语 + 主菜单） | `bot/locales/` |
| 2.9 | /cancel 命令 — 清除 FSM 状态，回主菜单 | handler |
| 2.10 | /lang 命令 — 快捷切换语言 | handler |

**验收标准：**
- 新用户 /start 看到三语欢迎语和语言选择按钮
- 选择语言后保存到数据库，进入主菜单
- 再次 /start 直接进入主菜单
- 菜单文案根据用户语言正确显示

---

## M3：售前咨询

**目标：** 用户可通过「查看商品清单」浏览商品并获取自动报价/说明；通过「配送说明」了解发货规则；通过「常见问题」自助查询。

| # | 任务 | 产出 |
|---|------|------|
| 3.1 | categories 表模型 + 迁移 | `bot/models/product.py` |
| 3.2 | products 表模型 + 迁移 | 同上 |
| 3.3 | product_variants 表模型 + 迁移（含自动回复字段） | 同上 |
| 3.4 | faq_items 表模型 + 迁移（type: faq/delivery） | `bot/models/faq.py` |
| 3.5 | 售前咨询入口菜单（查看商品清单/配送说明/常见问题） | `bot/handlers/presale.py` |
| 3.6 | 商品分类列表展示（两级分类） | handler + keyboard |
| 3.7 | 商品列表展示（按分类筛选 + 分页） | handler + keyboard |
| 3.8 | 规格选择列表（工业/开源/特殊等） | handler + keyboard |
| 3.9 | 自动回复逻辑：有预设 → 展示；无预设 → 转人工 | service |
| 3.10 | 配送说明展示（从 faq_items type=delivery 读取） | handler |
| 3.11 | 常见问题列表（分页）+ FAQ 详情 | handler |
| 3.12 | PresaleCallback 定义 | `bot/keyboards/callbacks.py` |
| 3.13 | 管理员编辑自动回复内容（基础版） | `bot/handlers/admin.py` |
| 3.14 | 管理员编辑 FAQ 和配送说明 | 同上 |

**验收标准：**
- 主菜单点击「售前咨询」进入三选项菜单
- 查看商品清单：分类 → 商品 → 规格 → 自动回复（有预设）或转人工（无预设）
- 配送说明：展示配送相关说明内容
- 常见问题：分页列表，点击展示详细答案
- 每个页面有「返回上级菜单」和「返回主菜单」按钮

---

## M4：售中下单（批发）

**目标：** 用户可提交批发订单需求，自动转接人工客服。

| # | 任务 | 产出 |
|---|------|------|
| 4.1 | wholesale_orders 表模型 + 迁移 | `bot/models/order.py` |
| 4.2 | 售中下单菜单 | `bot/handlers/order.py` |
| 4.3 | 批发订单 FSM 状态定义 | `bot/states/order.py` |
| 4.4 | 等待用户留言（数量和型号）的状态处理 | handler |
| 4.5 | 接收留言 → 创建批发订单记录 | service |
| 4.6 | 将留言转发到客服群组 | `bot/services/notification.py` |
| 4.7 | 通知用户已转接客服 | handler |
| 4.8 | 超时提示（10 分钟未输入） | handler |

**验收标准：**
- 点击「批发订单」提示用户输入需求
- 用户发送留言后，Bot 自动转发给客服群组
- 用户收到「已转接」提示
- 批发订单记录保存到数据库

---

## M5：售后支持

**目标：** 售后支持入口菜单，包含三个子模块，统一从主菜单「售后支持」进入。

| # | 任务 | 产出 |
|---|------|------|
| 5.1 | 售后支持入口菜单（订单状态查询/物流查询/设备支持） | `bot/handlers/aftersale.py` |
| 5.2 | AftersaleCallback 定义（aftersale:order_status / logistics / device） | `bot/keyboards/callbacks.py` |

**验收标准：**
- 主菜单点击「售后支持」展示三个子入口
- 每个子入口各自进入对应流程

---

## M5a：售后支持 → 订单状态查询

**目标：** 用户输入订单号查询发货状态，未发货时调用 LLM 自动回复，触发 5 次后转特定人工。

| # | 任务 | 产出 |
|---|------|------|
| 5a.1 | aftersale_queries 表模型 + 迁移 | `bot/models/` |
| 5a.2 | 聚水潭 API 封装（OAuth2 授权 + 订单查询） | `bot/services/jushuitan.py` |
| 5a.3 | 聚水潭 token 缓存（Redis） | service |
| 5a.4 | FSM：等待用户输入订单号 | `bot/handlers/aftersale.py` |
| 5a.5 | 调用聚水潭 API 查询，已发货 → 引导物流查询 | service + handler |
| 5a.6 | 未发货 → 调用 LLM（GPT/Claude）生成拖延回复 | `bot/services/ai_reply.py` |
| 5a.7 | Redis 计数器 `ai_reply:{user_id}:{order_id}` | service |
| 5a.8 | 触发 5 次 → 自动转**特定人工**（区别于普通客服群组） | handler + service |
| 5a.9 | 持久化查询记录 + 聚水潭 API 异常处理 | service |

**验收标准：**
- 已发货 → 展示发货信息，提供「查询物流」按钮
- 未发货 → LLM 生成拖延回复，计数 +1
- 第 5 次 → 自动转特定人工，附带历史记录

---

## M5b：售后支持 → 物流查询

**目标：** 用户选择发货地和物流商，输入跟踪号后自动查询物流轨迹。

| # | 任务 | 产出 |
|---|------|------|
| 5b.1 | logistics_queries 表模型 + 迁移 | `bot/models/` |
| 5b.2 | LogisticsTracker 抽象基类 | `bot/services/logistics_tracker.py` |
| 5b.3 | CDEKTracker / RUPostTracker / CainiaoTracker / AirFreightTracker 实现 | 各 tracker 文件 |
| 5b.4 | LogisticsTrackerFactory 工厂 | service |
| 5b.5 | FSM：选择发货地（莫斯科/中国）→ 选物流商 → 输入跟踪号 | `bot/handlers/logistics.py` |
| 5b.6 | 调用物流 API 查询并展示轨迹，结果缓存 30 分钟 | service |
| 5b.7 | 「刷新」按钮 + API 异常处理 | handler |
| 5b.8 | 持久化查询记录 | service |

**验收标准：**
- 选发货地 → 选物流商 → 输入跟踪号 → 展示轨迹
- 中国发货无需选物流商
- 30 分钟缓存生效，API 失败给出友好提示

---

## M5c：售后支持 → 设备支持

**目标：** 用户可查询序列号归属公司，提交设备问题，系统自动处理或转人工。

| # | 任务 | 产出 |
|---|------|------|
| 5c.1 | device_serial_queries 表模型 + 迁移 | `bot/models/device.py` |
| 5c.2 | device_tickets 表模型 + 迁移 | 同上 |
| 5c.3 | 设备支持入口菜单（查询序列号/设备问题/更多选项） | `bot/handlers/device.py` |
| 5c.4 | 查询序列号：FSM 接收序列号 → 预留接口查询 → 展示所属公司 | handler + service |
| 5c.5 | 设备问题：选类型（固件/硬件/软件/远程）→ 提交信息 → 处理或转人工 | handler + service |
| 5c.6 | 更多选项：选类型（固件/硬件/远程）→ 提交授权码+说明 → 处理或转人工 | handler + service |
| 5c.7 | DeviceCallback 定义 + 工单持久化 | callbacks + service |

**验收标准：**
- 查询序列号：输入序列号 → 返回所属公司信息（或未找到提示）
- 设备问题/更多选项：提交后机器人完成或转人工
- 工单保存到数据库

---

## M6：客服系统（转人工）

**目标：** 实现两条转人工通道：普通客服（客服合作菜单）和特定人工（售后 AI 触发 5 次）。

| # | 任务 | 产出 |
|---|------|------|
| 6.1 | support_tickets 表模型 + 迁移 | `bot/models/ticket.py` |
| 6.2 | support_messages 表模型 + 迁移 | 同上 |
| 6.3 | 配置两个客服通道：普通客服群组 + 特定人工（环境变量区分） | `bot/config.py` |
| 6.4 | 客服合作菜单（商务合作/批发咨询/转普通人工） | `bot/handlers/support.py` |
| 6.5 | 转人工 → 创建工单 → 按类型通知对应群组/账号 | handler + service |
| 6.6 | 客服认领工单（群组内按钮） | handler |
| 6.7 | 用户 ↔ 客服消息双向中转 | handler |
| 6.8 | 客服关闭工单，通知用户 | handler |
| 6.9 | 无人认领超时提醒管理员 | 后台任务 |

**验收标准：**
- 普通转人工 → 通知普通客服群组
- 售后 AI 第 5 次触发 → 通知特定人工（不同账号/群组）
- 双向消息中转正常，关闭工单通知用户

---

## M7：国际化完善

**目标：** 所有用户可见文案完成中/英/俄三语翻译。

| # | 任务 | 产出 |
|---|------|------|
| 9.1 | 提取所有 handler 中的文案为翻译 key | 翻译模板 |
| 9.2 | 中文翻译文件完善 | `locales/zh/` |
| 9.3 | 英文翻译文件完善 | `locales/en/` |
| 9.4 | 俄语翻译文件完善 | `locales/ru/` |
| 9.5 | 商品名称/分类名称多语言展示 | handler 逻辑 |
| 9.6 | AI 回复多语言（根据用户语言生成） | `ai_reply.py` |
| 9.7 | 错误消息多语言 | 翻译文件 |
| 9.8 | 全流程三语切换验证 | 测试用例 |

**验收标准：**
- 所有菜单、提示、错误信息均有中/英/俄翻译
- 切换语言后所有页面文案正确切换
- AI 回复根据用户语言生成对应语言内容
- 无硬编码文案遗漏

---

## M10：部署与运维

**目标：** 在华为云完成生产部署，配置监控和日志。

| # | 任务 | 产出 |
|---|------|------|
| 10.1 | 华为云 ECS 服务器环境配置 | 服务器环境 |
| 10.2 | Docker 镜像优化（多阶段构建减小体积） | 优化后的 Dockerfile |
| 10.3 | Nginx 反向代理 + SSL 配置（Let's Encrypt） | Nginx 配置文件 |
| 10.4 | Webhook 模式配置与验证 | 生产配置 |
| 10.5 | MySQL 数据库初始化与安全加固 | 数据库配置 |
| 10.6 | Redis 配置与密码加固 | Redis 配置 |
| 10.7 | 结构化日志输出配置 | 日志配置 |
| 10.8 | 健康检查接口 | 健康检查端点 |
| 10.9 | 数据库定时备份脚本 | 备份脚本 |
| 10.10 | Docker restart policy（自动重启） | Docker 配置 |
| 10.11 | 上线前全功能回归测试 | 测试报告 |

**验收标准：**
- `docker-compose up -d` 一键部署所有服务
- Webhook 模式正常接收 Telegram 消息
- SSL 证书正常，HTTPS 访问通畅
- Bot 进程异常退出能自动重启
- 数据库有定时备份

---

## 模块依赖关系图

```
M1（基础搭建）
 │
 └── M2（用户系统）
      │
      ├── M3（售前咨询）
      │
      ├── M4（售中下单/批发）
      │
      ├── M5（售后支持入口）
      │    ├── M5a（订单状态查询 + 聚水潭 + LLM）
      │    ├── M5b（物流查询）
      │    └── M5c（设备支持）
      │
      └── M6（客服系统 — 两条转人工通道）
           │
           └── M7（国际化完善）── 依赖 M2~M6 全部完成
                │
                └── M8（部署与运维）── 最后执行
```

## 外部依赖清单

开发前需要提前申请/确认的外部账号和 API：

| 服务 | 用途 | 需要信息 |
|------|------|---------|
| Telegram BotFather | 创建 Bot | Bot Token |
| 聚水潭 ERP | 售后订单查询 | App Key、App Secret |
| CDEK API | 物流查询 | Client ID、Client Secret |
| 俄罗斯邮政 API | 物流查询 | API Token |
| 菜鸟物流 API | 物流查询 | App Key、App Secret |
| 华为云 ECS | 服务器 | 服务器 IP、SSH 密钥 |
| 域名 + SSL | Webhook HTTPS | 域名、Let's Encrypt |
