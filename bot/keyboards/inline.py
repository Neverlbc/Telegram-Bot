"""InlineKeyboard 构建器 — 统一管理所有键盘布局."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callbacks import (
    AftersaleCallback,
    DeviceCallback,
    LangCallback,
    LogisticsCallback,
    MenuCallback,
    NavCallback,
    OrderCallback,
    PresaleCallback,
    SupportCallback,
)


# ── 导航按钮 ──────────────────────────────────────────

def nav_buttons(back_target: str = "", lang: str = "zh") -> list[list[InlineKeyboardButton]]:
    """生成统一的「返回上级」和「返回主菜单」按钮行."""
    texts = {
        "zh": {"back": "◀️ 返回上级菜单", "home": "🏠 返回主菜单"},
        "en": {"back": "◀️ Back", "home": "🏠 Main Menu"},
        "ru": {"back": "◀️ Назад", "home": "🏠 Главное меню"},
    }
    t = texts.get(lang, texts["zh"])
    return [
        [InlineKeyboardButton(
            text=t["back"],
            callback_data=NavCallback(action="back", target=back_target).pack(),
        )],
        [InlineKeyboardButton(
            text=t["home"],
            callback_data=NavCallback(action="home").pack(),
        )],
    ]


# ── 语言选择 ──────────────────────────────────────────

def language_keyboard() -> InlineKeyboardMarkup:
    """语言选择键盘."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇨🇳 中文", callback_data=LangCallback(code="zh").pack()),
    )
    builder.row(
        InlineKeyboardButton(text="🇬🇧 English", callback_data=LangCallback(code="en").pack()),
    )
    builder.row(
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data=LangCallback(code="ru").pack()),
    )
    return builder.as_markup()


# ── 设置与个人中心 ────────────────────────────────────

def settings_menu_keyboard(lang: str = "zh", show_profile: bool = True) -> InlineKeyboardMarkup:
    """设置面板键盘.

    Args:
        show_profile: 如果在个人中心页面，就只显示切换语言等；如果是在设置列表，显示个人中心和语言切换。
    """
    texts = {
        "zh": {"profile": "👤 个人中心", "lang": "🌐 切换语言"},
        "en": {"profile": "👤 Profile", "lang": "🌐 Language"},
        "ru": {"profile": "👤 Профиль", "lang": "🌐 Язык"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    
    if show_profile:
        builder.row(
            InlineKeyboardButton(text=t["profile"], callback_data=MenuCallback(action="profile").pack()),
        )
        builder.row(
            InlineKeyboardButton(text=t["lang"], callback_data=MenuCallback(action="setting_lang").pack()),
        )
        for row in nav_buttons("menu", lang):
            builder.row(*row)
    else:
        # 当已经在个人中心页面时，提供直接切换语言的快捷方式，并且后退目标改为设置首页
        builder.row(
            InlineKeyboardButton(text=t["lang"], callback_data=MenuCallback(action="setting_lang").pack()),
        )
        for row in nav_buttons("settings", lang):
            builder.row(*row)
            
    return builder.as_markup()

# ── 主菜单 ────────────────────────────────────────────

def main_menu_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """主菜单键盘 — 5 个功能入口."""
    # 多语言文案
    texts = {
        "zh": {
            "presale": "🛍 售前咨询",
            "order": "📦 售中下单",
            "aftersale": "🔧 售后支持",
            "support": "🤝 需要合作",
            "settings": "⚙️ 设置",
        },
        "en": {
            "presale": "🛍 Pre-sale",
            "order": "📦 Order",
            "aftersale": "🔧 After-sale",
            "support": "🤝 Cooperation",
            "settings": "⚙️ Settings",
        },
        "ru": {
            "presale": "🛍 Консультация",
            "order": "📦 Заказ",
            "aftersale": "🔧 Поддержка",
            "support": "🤝 Сотрудничество",
            "settings": "⚙️ Настройки",
        },
    }

    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t["presale"], callback_data=MenuCallback(action="presale").pack()),
        InlineKeyboardButton(text=t["order"], callback_data=MenuCallback(action="order").pack()),
    )
    builder.row(
        InlineKeyboardButton(text=t["aftersale"], callback_data=MenuCallback(action="aftersale").pack()),
        InlineKeyboardButton(text=t["support"], callback_data=MenuCallback(action="support").pack()),
    )
    builder.row(
        InlineKeyboardButton(text=t["settings"], callback_data=MenuCallback(action="settings").pack()),
    )
    return builder.as_markup()


# ── 售前咨询入口 ──────────────────────────────────────

def presale_menu_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """售前咨询入口键盘."""
    texts = {
        "zh": {"catalog": "📋 查看商品清单", "delivery": "🚚 配送说明", "faq": "❓ 常见问题"},
        "en": {"catalog": "📋 Product Catalog", "delivery": "🚚 Delivery Info", "faq": "❓ FAQ"},
        "ru": {"catalog": "📋 Каталог", "delivery": "🚚 Доставка", "faq": "❓ FAQ"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t["catalog"], callback_data=PresaleCallback(action="catalog").pack()))
    builder.row(InlineKeyboardButton(text=t["delivery"], callback_data=PresaleCallback(action="delivery").pack()))
    builder.row(InlineKeyboardButton(text=t["faq"], callback_data=PresaleCallback(action="faq").pack()))
    for row in nav_buttons("menu", lang):
        builder.row(*row)
    return builder.as_markup()


# ── 售中下单 — 产品类型选择 ────────────────────────────

def order_product_type_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """售中下单 — 询问产品类型."""
    texts = {
        "zh": {"thermal": "🌡 热成像仪", "power": "⚡ 动力工具", "wholesale": "📦 批发订单"},
        "en": {"thermal": "🌡 Thermal Imager", "power": "⚡ Power Tools", "wholesale": "📦 Wholesale Order"},
        "ru": {"thermal": "🌡 Тепловизор", "power": "⚡ Инструменты", "wholesale": "📦 Оптовый заказ"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["thermal"], callback_data=OrderCallback(action="category", cat_id="thermal").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["power"], callback_data=OrderCallback(action="aliexpress").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["wholesale"], callback_data=OrderCallback(action="wholesale").pack(),
    ))
    for row in nav_buttons("menu", lang):
        builder.row(*row)
    return builder.as_markup()


def order_thermal_subcategory_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """售中下单 — 热成像仪子分类选择."""
    texts = {
        "zh": {"industrial": "🏭 工业", "hunting": "🎯 狩猎", "special": "⭐ 特殊"},
        "en": {"industrial": "🏭 Industrial", "hunting": "🎯 Hunting", "special": "⭐ Special"},
        "ru": {"industrial": "🏭 Промышленные", "hunting": "🎯 Охота", "special": "⭐ Специальные"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["industrial"], callback_data=OrderCallback(action="transfer", sub="industrial").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["hunting"], callback_data=OrderCallback(action="transfer", sub="hunting").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["special"], callback_data=OrderCallback(action="transfer", sub="special").pack(),
    ))
    # 返回上级 → 产品类型选择
    back_texts = {
        "zh": "◀️ 返回产品类型", "en": "◀️ Back", "ru": "◀️ Назад",
    }
    builder.row(InlineKeyboardButton(
        text=back_texts.get(lang, back_texts["zh"]),
        callback_data=OrderCallback(action="category", cat_id="back").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text={"zh": "🏠 返回主菜单", "en": "🏠 Main Menu", "ru": "🏠 Главное меню"}.get(lang, "🏠 返回主菜单"),
        callback_data=NavCallback(action="home").pack(),
    ))
    return builder.as_markup()


# ── 售后支持入口 ──────────────────────────────────────

def aftersale_menu_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """售后支持入口键盘 — 三个子模块."""
    texts = {
        "zh": {"order": "📋 订单状态查询", "logistics": "🚛 物流查询", "device": "🔧 设备支持"},
        "en": {"order": "📋 Order Status", "logistics": "🚛 Logistics", "device": "🔧 Device Support"},
        "ru": {"order": "📋 Статус заказа", "logistics": "🚛 Логистика", "device": "🔧 Устройства"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["order"], callback_data=AftersaleCallback(action="order_status").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["logistics"], callback_data=AftersaleCallback(action="logistics").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["device"], callback_data=AftersaleCallback(action="device").pack(),
    ))
    for row in nav_buttons("menu", lang):
        builder.row(*row)
    return builder.as_markup()


# ── 物流查询 — 选择发货地 ─────────────────────────────

def logistics_origin_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """物流查询 — 选择发货地."""
    texts = {
        "zh": {"moscow": "🇷🇺 莫斯科发货", "china": "🇨🇳 中国发货"},
        "en": {"moscow": "🇷🇺 Moscow", "china": "🇨🇳 China"},
        "ru": {"moscow": "🇷🇺 Москва", "china": "🇨🇳 Китай"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["moscow"], callback_data=LogisticsCallback(action="origin", origin="moscow").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["china"], callback_data=LogisticsCallback(action="origin", origin="china").pack(),
    ))
    for row in nav_buttons("aftersale", lang):
        builder.row(*row)
    return builder.as_markup()


# ── 物流查询 — 选择物流商 ─────────────────────────────

def logistics_carrier_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """莫斯科发货 — 选择物流商."""
    carriers = [
        ("CDEK", "cdek"),
        ("RU Post", "rupost"),
        ("Cainiao", "cainiao"),
        ("✈️ 空运" if lang == "zh" else "✈️ Air Freight", "airfreight"),
    ]
    builder = InlineKeyboardBuilder()
    for text, carrier in carriers:
        builder.row(InlineKeyboardButton(
            text=text,
            callback_data=LogisticsCallback(action="carrier", origin="moscow", carrier=carrier).pack(),
        ))
    for row in nav_buttons("logistics", lang):
        builder.row(*row)
    return builder.as_markup()


# ── 设备支持入口 ──────────────────────────────────────

def device_menu_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """设备支持入口键盘."""
    texts = {
        "zh": {"serial": "🔍 查询序列号", "issue": "🛠 设备问题", "more": "📝 更多选项"},
        "en": {"serial": "🔍 Serial Query", "issue": "🛠 Device Issue", "more": "📝 More Options"},
        "ru": {"serial": "🔍 Серийный номер", "issue": "🛠 Проблема", "more": "📝 Ещё"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["serial"], callback_data=DeviceCallback(action="serial").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["issue"], callback_data=DeviceCallback(action="issue").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["more"], callback_data=DeviceCallback(action="more").pack(),
    ))
    for row in nav_buttons("aftersale", lang):
        builder.row(*row)
    return builder.as_markup()


# ── 客服合作 ──────────────────────────────────────────

def support_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """客服合作键盘 — 我是博主 / 我是批发商 / 狩猎俱乐部."""
    texts = {
        "zh": {"blogger": "📣 我是博主", "wholesaler": "📦 我是批发商", "huntclub": "🎯 狩猎俱乐部"},
        "en": {"blogger": "📣 I'm a Blogger", "wholesaler": "📦 I'm a Wholesaler", "huntclub": "🎯 Hunting Club"},
        "ru": {"blogger": "📣 Блогер", "wholesaler": "📦 Оптовик", "huntclub": "🎯 Охотничий клуб"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["blogger"], callback_data=SupportCallback(action="blogger").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["wholesaler"], callback_data=SupportCallback(action="wholesaler").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["huntclub"], callback_data=SupportCallback(action="huntclub").pack(),
    ))
    for row in nav_buttons("menu", lang):
        builder.row(*row)
    return builder.as_markup()
