# 数据库设计文档

## 1. ER 关系图

```
┌──────────┐     ┌────────────┐     ┌──────────┐
│  users   │     │ categories │     │ products │
│──────────│     │────────────│     │──────────│
│ id (PK)  │     │ id (PK)    │◄──┐ │ id (PK)  │
│ tg_id    │     │ parent_id  │───┘ │ cat_id   │──► categories
│ language │     │ name_zh    │     │ name_zh  │
│ ...      │     │ ...        │     │ ...      │
└────┬─────┘     └────────────┘     └──────────┘
     │
     │  ┌──────────────────┐     ┌─────────────────┐
     │  │  wholesale_orders │     │ support_tickets  │
     │  │──────────────────│     │─────────────────│
     └─►│ user_id          │     │ user_id         │──► users
        │ message          │     │ agent_id        │
        │ status           │     │ type            │
        └──────────────────┘     │ status          │
                                 └────────┬────────┘
                                          │
                                 ┌────────▼────────┐
                                 │ support_messages │
                                 │─────────────────│
                                 │ ticket_id        │
                                 │ sender_id        │
                                 │ content          │
                                 └──────────────────┘

┌──────────────────┐     ┌─────────────────────┐
│  logistics_queries│     │ serial_queries       │
│──────────────────│     │─────────────────────│
│ user_id          │──► users  │ user_id        │──► users
│ tracking_no      │     │ serial_no            │
│ carrier          │     │ query_type           │
│ origin           │     │ result               │
│ result_cache     │     └─────────────────────┘
└──────────────────┘
```

## 2. 表结构详细设计

### 2.1 users — 用户表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 内部主键 |
| `telegram_id` | BIGINT | UNIQUE, NOT NULL | Telegram 用户 ID |
| `username` | VARCHAR(64) | NULL | Telegram 用户名 |
| `first_name` | VARCHAR(128) | NULL | 名字 |
| `last_name` | VARCHAR(128) | NULL | 姓氏 |
| `language` | ENUM('zh','en','ru') | NOT NULL, DEFAULT 'zh' | 选择的语言 |
| `is_blocked` | TINYINT(1) | NOT NULL, DEFAULT 0 | 是否被封禁 |
| `is_admin` | TINYINT(1) | NOT NULL, DEFAULT 0 | 是否管理员 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 首次使用时间 |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE CURRENT_TIMESTAMP | 最后更新时间 |

**索引：**
- `uk_telegram_id` — UNIQUE(telegram_id)
- `idx_created_at` — INDEX(created_at)

---

### 2.2 categories — 商品分类表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT UNSIGNED | PK, AUTO_INCREMENT | 分类 ID |
| `parent_id` | INT UNSIGNED | NULL, FK → categories.id | 父分类（NULL 为一级分类） |
| `name_zh` | VARCHAR(128) | NOT NULL | 中文名称 |
| `name_en` | VARCHAR(128) | NOT NULL | 英文名称 |
| `name_ru` | VARCHAR(128) | NOT NULL | 俄语名称 |
| `sort_order` | INT | NOT NULL, DEFAULT 0 | 排序权重（越小越靠前） |
| `is_active` | TINYINT(1) | NOT NULL, DEFAULT 1 | 是否启用 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**索引：**
- `idx_parent_id` — INDEX(parent_id)
- `idx_sort_active` — INDEX(sort_order, is_active)

**说明：** 支持两级分类结构（一级：数码商品/流量、账证类别等；二级：动力工具、市场调研等）。

---

### 2.3 products — 商品表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT UNSIGNED | PK, AUTO_INCREMENT | 商品 ID |
| `category_id` | INT UNSIGNED | NOT NULL, FK → categories.id | 所属分类 |
| `name_zh` | VARCHAR(256) | NOT NULL | 中文名称 |
| `name_en` | VARCHAR(256) | NOT NULL | 英文名称 |
| `name_ru` | VARCHAR(256) | NOT NULL | 俄语名称 |
| `description_zh` | TEXT | NULL | 中文描述 |
| `description_en` | TEXT | NULL | 英文描述 |
| `description_ru` | TEXT | NULL | 俄语描述 |
| `is_active` | TINYINT(1) | NOT NULL, DEFAULT 1 | 是否上架 |
| `sort_order` | INT | NOT NULL, DEFAULT 0 | 排序权重 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE CURRENT_TIMESTAMP | 更新时间 |

**索引：**
- `idx_category_active` — INDEX(category_id, is_active)
- `idx_sort_order` — INDEX(sort_order)

---

### 2.4 product_variants — 商品规格与自动回复表

售前咨询中，每个商品可以有多个规格（工业/开源/特殊），每个规格可配置自动回复内容。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT UNSIGNED | PK, AUTO_INCREMENT | 规格 ID |
| `product_id` | INT UNSIGNED | NOT NULL, FK → products.id | 所属商品 |
| `variant_key` | VARCHAR(64) | NOT NULL | 规格标识（industrial / opensource / special） |
| `name_zh` | VARCHAR(128) | NOT NULL | 中文规格名称 |
| `name_en` | VARCHAR(128) | NOT NULL | 英文规格名称 |
| `name_ru` | VARCHAR(128) | NOT NULL | 俄语规格名称 |
| `auto_reply_zh` | TEXT | NULL | 中文自动回复内容（为空则转人工） |
| `auto_reply_en` | TEXT | NULL | 英文自动回复内容 |
| `auto_reply_ru` | TEXT | NULL | 俄语自动回复内容 |
| `is_active` | TINYINT(1) | NOT NULL, DEFAULT 1 | 是否启用 |
| `sort_order` | INT | NOT NULL, DEFAULT 0 | 排序权重 |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE CURRENT_TIMESTAMP | 最后编辑时间 |

**索引：**
- `uk_product_variant` — UNIQUE(product_id, variant_key)

**说明：**
- `auto_reply_*` 字段为空时，Bot 自动触发转人工逻辑
- 管理员可通过 `/admin` 后台随时编辑各规格的自动回复内容

---

### 2.5 faq_items — FAQ 与配送说明表

统一存储「常见问题」和「配送说明」两类内容。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT UNSIGNED | PK, AUTO_INCREMENT | 条目 ID |
| `type` | ENUM('faq','delivery') | NOT NULL | 类型：常见问题 / 配送说明 |
| `question_zh` | VARCHAR(256) | NULL | 中文问题/标题（配送说明可为空） |
| `question_en` | VARCHAR(256) | NULL | 英文问题/标题 |
| `question_ru` | VARCHAR(256) | NULL | 俄语问题/标题 |
| `answer_zh` | TEXT | NOT NULL | 中文答案/内容 |
| `answer_en` | TEXT | NOT NULL | 英文答案/内容 |
| `answer_ru` | TEXT | NOT NULL | 俄语答案/内容 |
| `sort_order` | INT | NOT NULL, DEFAULT 0 | 排序权重 |
| `is_active` | TINYINT(1) | NOT NULL, DEFAULT 1 | 是否启用 |
| `updated_at` | DATETIME | NOT NULL, ON UPDATE CURRENT_TIMESTAMP | 最后编辑时间 |

**索引：**
- `idx_type_active` — INDEX(type, is_active, sort_order)

---

### 2.4 wholesale_orders — 批发订单表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 订单 ID |
| `user_id` | BIGINT UNSIGNED | NOT NULL, FK → users.id | 下单用户 |
| `message` | TEXT | NOT NULL | 用户留言内容（数量和型号） |
| `status` | ENUM(...) | NOT NULL, DEFAULT 'pending' | 订单状态（见枚举定义） |
| `agent_id` | BIGINT UNSIGNED | NULL, FK → users.id | 负责客服 |
| `telegram_message_id` | BIGINT | NULL | 转发到客服群的消息 ID |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `assigned_at` | DATETIME | NULL | 客服认领时间 |
| `closed_at` | DATETIME | NULL | 完成时间 |

**索引：**
- `idx_user_id` — INDEX(user_id)
- `idx_status` — INDEX(status)
- `idx_created_at` — INDEX(created_at)

---

### 2.5 logistics_queries — 物流查询记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 查询记录 ID |
| `user_id` | BIGINT UNSIGNED | NOT NULL, FK → users.id | 查询用户 |
| `tracking_no` | VARCHAR(128) | NOT NULL | 物流跟踪号 |
| `carrier` | ENUM(...) | NOT NULL | 物流商（见枚举定义） |
| `origin` | ENUM('moscow','china') | NOT NULL | 发货地 |
| `result_cache` | JSON | NULL | 最近一次查询结果缓存 |
| `last_queried_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 最近查询时间 |
| `query_count` | INT | NOT NULL, DEFAULT 1 | 查询次数 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 首次查询时间 |

**索引：**
- `idx_user_id` — INDEX(user_id)
- `idx_tracking_no` — INDEX(tracking_no)
- `uk_user_tracking` — UNIQUE(user_id, tracking_no, carrier)

---

### 2.6 aftersale_queries — 售后查询记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 记录 ID |
| `user_id` | BIGINT UNSIGNED | NOT NULL, FK → users.id | 查询用户 |
| `order_id` | VARCHAR(64) | NOT NULL | 聚水潭订单号 |
| `query_count` | INT | NOT NULL, DEFAULT 1 | 查询次数（≥5 转人工） |
| `last_status` | VARCHAR(32) | NULL | 最后查询到的状态 |
| `escalated` | TINYINT(1) | NOT NULL, DEFAULT 0 | 是否已转人工 |
| `last_queried_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 最近查询时间 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 首次查询时间 |

**索引：**
- `idx_user_id` — INDEX(user_id)
- `uk_user_order` — UNIQUE(user_id, order_id)

**说明：** 配合 Redis `ai_reply:{user_id}:{order_id}` 计数器使用。Redis 负责实时计数，该表负责持久化记录和 escalated 状态。

---

### 2.7 device_serial_queries — 序列号查询记录表

用户输入序列号，Bot 查询该序列号属于哪家公司的产品。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 记录 ID |
| `user_id` | BIGINT UNSIGNED | NOT NULL, FK → users.id | 查询用户 |
| `serial_no` | VARCHAR(128) | NOT NULL | 用户输入的序列号 |
| `company_name` | VARCHAR(256) | NULL | 查询到的所属公司名称 |
| `product_info` | JSON | NULL | 产品详细信息（型号、归属等） |
| `found` | TINYINT(1) | NOT NULL, DEFAULT 0 | 是否查到结果 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 查询时间 |

**索引：**
- `idx_user_id` — INDEX(user_id)
- `idx_serial_no` — INDEX(serial_no)

---

### 2.8 device_tickets — 设备问题工单表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 工单 ID |
| `user_id` | BIGINT UNSIGNED | NOT NULL, FK → users.id | 用户 |
| `section` | ENUM('issue','more') | NOT NULL | 来源（设备问题/更多选项） |
| `issue_type` | ENUM('firmware','hardware','software','remote') | NOT NULL | 问题类型 |
| `content` | TEXT | NOT NULL | 用户提交的内容（数量+型号+序列号 或 授权码+说明） |
| `status` | ENUM('pending','processing','done','escalated') | NOT NULL, DEFAULT 'pending' | 处理状态 |
| `handler` | ENUM('robot','human') | NULL | 处理方式 |
| `result` | TEXT | NULL | 处理结果 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 提交时间 |
| `resolved_at` | DATETIME | NULL | 完成时间 |

**索引：**
- `idx_user_id` — INDEX(user_id)
- `idx_status` — INDEX(status)
- `idx_section_type` — INDEX(section, issue_type)

---

### 2.8 support_tickets — 客服工单表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 工单 ID |
| `user_id` | BIGINT UNSIGNED | NOT NULL, FK → users.id | 发起用户 |
| `agent_id` | BIGINT UNSIGNED | NULL, FK → users.id | 接待客服 |
| `type` | ENUM(...) | NOT NULL | 工单类型（见枚举定义） |
| `status` | ENUM(...) | NOT NULL, DEFAULT 'pending' | 工单状态（见枚举定义） |
| `subject` | VARCHAR(256) | NULL | 主题/摘要 |
| `ref_order_id` | VARCHAR(64) | NULL | 关联订单号（如有） |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `assigned_at` | DATETIME | NULL | 认领时间 |
| `closed_at` | DATETIME | NULL | 关闭时间 |

**索引：**
- `idx_user_id` — INDEX(user_id)
- `idx_agent_status` — INDEX(agent_id, status)
- `idx_status` — INDEX(status)

---

### 2.9 support_messages — 客服消息记录表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 消息 ID |
| `ticket_id` | BIGINT UNSIGNED | NOT NULL, FK → support_tickets.id | 关联工单 |
| `sender_id` | BIGINT | NOT NULL | 发送者 Telegram ID |
| `sender_role` | ENUM('user','agent') | NOT NULL | 发送者角色 |
| `message_type` | ENUM('text','photo','document','voice') | NOT NULL, DEFAULT 'text' | 消息类型 |
| `content` | TEXT | NOT NULL | 消息内容 |
| `telegram_message_id` | BIGINT | NULL | Telegram 消息 ID |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 发送时间 |

**索引：**
- `idx_ticket_id` — INDEX(ticket_id)
- `idx_created_at` — INDEX(created_at)

## 3. 枚举值定义

### 3.1 批发订单状态（wholesale_orders.status）

| 值 | 说明 |
|----|------|
| `pending` | 待接入（等待客服认领） |
| `assigned` | 已认领 |
| `in_progress` | 处理中 |
| `closed` | 已完成 |
| `cancelled` | 已取消 |

### 3.2 物流商（logistics_queries.carrier）

| 值 | 说明 | 适用发货地 |
|----|------|----------|
| `cdek` | CDEK 快递 | 莫斯科 |
| `rupost` | 俄罗斯邮政 | 莫斯科 |
| `cainiao` | 菜鸟物流 | 莫斯科 |
| `airfreight` | 空运 | 莫斯科 |
| `china_domestic` | 中国发货（通用） | 中国 |

### 3.3 工单类型（support_tickets.type）

| 值 | 说明 |
|----|------|
| `general` | 一般咨询 |
| `business` | 商务合作 |
| `wholesale` | 批发咨询 |
| `aftersale` | 售后问题（AI 触发 5 次转人工） |
| `logistics` | 物流问题 |

### 3.4 工单状态（support_tickets.status）

| 值 | 说明 |
|----|------|
| `pending` | 待接入 |
| `assigned` | 已认领 |
| `in_progress` | 处理中 |
| `closed` | 已关闭 |

### 3.5 用户语言（users.language）

| 值 | 说明 |
|----|------|
| `zh` | 中文 |
| `en` | English |
| `ru` | Русский |

### 3.6 设备问题类型（device_tickets.issue_type）

| 值 | 说明 | 适用 section |
|----|------|-------------|
| `firmware` | 固件类 | issue / more |
| `hardware` | 硬件类 | issue / more |
| `software` | 软件类 | issue only |
| `remote` | 远程类 | issue / more |

## 4. Redis 键设计

| Key 格式 | 类型 | TTL | 用途 |
|---------|------|-----|------|
| `ai_reply:{user_id}:{order_id}` | String (int) | 7 天 | 售后 AI 回复触发计数 |
| `logistics_cache:{carrier}:{tracking_no}` | String (JSON) | 30 分钟 | 物流查询结果缓存 |
| `throttle:{user_id}` | String (int) | 1 秒 | 全局频率限制计数 |
| `fsm:{bot_id}:{chat_id}:{user_id}:state` | String | 永久（由 aiogram 管理） | FSM 当前状态 |
| `fsm:{bot_id}:{chat_id}:{user_id}:data` | String (JSON) | 永久（由 aiogram 管理） | FSM 数据 |

## 5. 数据约束与规则

### 5.1 字符集

- 数据库字符集：`utf8mb4`
- 排序规则：`utf8mb4_unicode_ci`
- 支持中文、英文、俄文及 emoji

### 5.2 数据保留策略

| 表 | 保留策略 |
|----|---------|
| users | 永久保留 |
| categories / products | 永久保留 |
| wholesale_orders | 永久保留 |
| aftersale_queries | 保留 180 天 |
| logistics_queries | 保留 90 天 |
| serial_queries | 保留 90 天 |
| support_tickets | 永久保留 |
| support_messages | 保留 180 天 |

### 5.3 聚水潭订单号说明

- 售后查询中的 `order_id` 来自聚水潭 ERP，非本系统生成
- 格式由聚水潭决定，本系统以 VARCHAR(64) 存储
- 查询时直接传入聚水潭 API，不做格式校验
