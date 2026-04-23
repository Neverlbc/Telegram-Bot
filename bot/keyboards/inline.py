"""InlineKeyboard 构建器 — 统一管理所有键盘布局."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callbacks import (
    InventoryCallback,
    LangCallback,
    MenuCallback,
    NavCallback,
    ServiceCenterCallback,
    VipCallback,
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
    """设置面板键盘."""
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
        builder.row(
            InlineKeyboardButton(text=t["lang"], callback_data=MenuCallback(action="setting_lang").pack()),
        )
        for row in nav_buttons("settings", lang):
            builder.row(*row)

    return builder.as_markup()


# ── 主菜单（新版 3 按钮）────────────────────────────

def main_menu_keyboard(lang: str = "zh", club_link: str = "") -> InlineKeyboardMarkup:
    """主菜单键盘 — 3 个功能入口."""
    texts = {
        "zh": {
            "inventory": "🔍 莫斯科现货查询",
            "service_center": "🛠 A-BF 俄罗斯服务中心",
            "club": "🌙 A-BF 晨夜俱乐部",
            "settings": "⚙️ 设置",
        },
        "en": {
            "inventory": "🔍 Moscow Inventory",
            "service_center": "🛠 A-BF Russia Service Center",
            "club": "🌙 A-BF Night Club",
            "settings": "⚙️ Settings",
        },
        "ru": {
            "inventory": "🔍 Наличие в Москве",
            "service_center": "🛠 Сервисный центр A-BF",
            "club": "🌙 Клуб A-BF",
            "settings": "⚙️ Настройки",
        },
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["inventory"],
        callback_data=InventoryCallback(action="menu").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["service_center"],
        callback_data=ServiceCenterCallback(action="menu").pack(),
    ))
    if club_link:
        builder.row(InlineKeyboardButton(text=t["club"], url=club_link))
    else:
        from bot.keyboards.callbacks import NavCallback as _Nav  # avoid circular at module level
        builder.row(InlineKeyboardButton(
            text=t["club"],
            callback_data=_Nav(action="home").pack(),  # fallback
        ))
    builder.row(InlineKeyboardButton(
        text=t["settings"],
        callback_data=MenuCallback(action="settings").pack(),
    ))
    return builder.as_markup()


# ── 莫斯科现货查询 ────────────────────────────────────

def inventory_menu_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """莫斯科现货查询 — 普通查询 / VIP查询."""
    texts = {
        "zh": {
            "public": "📋 普通查询",
            "vip": "⭐ VIP 查询（输入密码）",
        },
        "en": {
            "public": "📋 Public Query",
            "vip": "⭐ VIP Query (enter password)",
        },
        "ru": {
            "public": "📋 Обычный запрос",
            "vip": "⭐ VIP-запрос (ввести пароль)",
        },
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["public"],
        callback_data=InventoryCallback(action="public_query").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["vip"],
        callback_data=InventoryCallback(action="vip_enter_password").pack(),
    ))
    for row in nav_buttons("menu", lang):
        builder.row(*row)
    return builder.as_markup()


def inventory_category_keyboard(lang: str = "zh", vip: bool = False) -> InlineKeyboardMarkup:
    """莫斯科现货查询 — 选择品类."""
    texts = {
        "zh": {"outdoor": "🏕 户外类"},
        "en": {"outdoor": "🏕 Outdoor"},
        "ru": {"outdoor": "🏕 Аутдор"},
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["outdoor"],
        callback_data=InventoryCallback(action="category", cat_id="outdoor", vip=vip).pack(),
    ))
    back_target = "inv_vip" if vip else "inv_public"
    for row in nav_buttons(back_target, lang):
        builder.row(*row)
    return builder.as_markup()


# ── A-BF 俄罗斯服务中心 ───────────────────────────────

def service_center_menu_keyboard(lang: str = "zh", service_link: str = "") -> InlineKeyboardMarkup:
    """服务中心主菜单."""
    texts = {
        "zh": {
            "info": "📄 服务中心说明",
            "link": "🔗 服务中心入口链接",
            "repair": "🔧 设备检修查询",
        },
        "en": {
            "info": "📄 Service Center Info",
            "link": "🔗 Service Center Link",
            "repair": "🔧 Device Repair Query",
        },
        "ru": {
            "info": "📄 О сервисном центре",
            "link": "🔗 Ссылка на сервисный центр",
            "repair": "🔧 Запрос ремонта",
        },
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["info"],
        callback_data=ServiceCenterCallback(action="info").pack(),
    ))
    if service_link:
        builder.row(InlineKeyboardButton(text=t["link"], url=service_link))
    else:
        builder.row(InlineKeyboardButton(
            text=t["link"],
            callback_data=ServiceCenterCallback(action="link").pack(),
        ))
    builder.row(InlineKeyboardButton(
        text=t["repair"],
        callback_data=ServiceCenterCallback(action="repair").pack(),
    ))
    for row in nav_buttons("menu", lang):
        builder.row(*row)
    return builder.as_markup()


def service_center_admin_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """服务中心管理员后台键盘."""
    texts = {
        "zh": {
            "notify": "📩 维修完成通知设置",
            "sn": "🔍 查询 SN 表",
        },
        "en": {
            "notify": "📩 Repair Completion Notifications",
            "sn": "🔍 Query SN List",
        },
        "ru": {
            "notify": "📩 Уведомления о завершении ремонта",
            "sn": "🔍 Запрос списка SN",
        },
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["notify"],
        callback_data=ServiceCenterCallback(action="admin_menu").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["sn"],
        callback_data=ServiceCenterCallback(action="sn_list").pack(),
    ))
    for row in nav_buttons("sc_menu", lang):
        builder.row(*row)
    return builder.as_markup()


# ── Vandych VIP 菜单 ─────────────────────────────────

def vip_menu_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    """Vandych VIP 隐藏菜单."""
    texts = {
        "zh": {
            "discount": "🎁 获取折扣",
            "shipping": "✈️ 支付空运",
            "wholesale": "📦 我需要批发",
        },
        "en": {
            "discount": "🎁 Get Discount",
            "shipping": "✈️ Pay Air Freight",
            "wholesale": "📦 I Need Wholesale",
        },
        "ru": {
            "discount": "🎁 Получить скидку",
            "shipping": "✈️ Оплатить авиадоставку",
            "wholesale": "📦 Оптовый заказ",
        },
    }
    t = texts.get(lang, texts["zh"])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=t["discount"],
        callback_data=VipCallback(action="discount").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["shipping"],
        callback_data=VipCallback(action="shipping").pack(),
    ))
    builder.row(InlineKeyboardButton(
        text=t["wholesale"],
        callback_data=VipCallback(action="wholesale").pack(),
    ))
    for row in nav_buttons("menu", lang):
        builder.row(*row)
    return builder.as_markup()
