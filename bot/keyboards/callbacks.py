"""CallbackData 工厂定义 — 所有回调数据类."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class LangCallback(CallbackData, prefix="lang"):
    """语言选择."""

    code: str  # zh / en / ru


class MenuCallback(CallbackData, prefix="menu"):
    """主菜单."""

    action: str  # presale / order / aftersale / support / settings


class PresaleCallback(CallbackData, prefix="presale"):
    """售前咨询."""

    action: str  # menu / catalog / delivery / faq / category / inventory / faq_detail
    cat_id: str = ""      # 顶级分类 key (如 "thermal", "power")
    sheet_key: str = ""   # sheet key (如 "thermal_industrial")
    faq_id: int = 0
    page: int = 1

class OrderCallback(CallbackData, prefix="order"):
    """售中下单."""

    action: str  # category / wholesale / aliexpress / transfer / confirm / cancel
    cat_id: str = ""    # 顶级分类 key (thermal / power)
    sub: str = ""       # 子分类 (industrial / hunting / special)


class AftersaleCallback(CallbackData, prefix="aftersale"):
    """售后支持."""

    action: str  # menu / order_status / logistics / device / query / status
    order_id: str = ""


class LogisticsCallback(CallbackData, prefix="logistics"):
    """物流查询."""

    action: str  # origin / carrier / track / refresh
    origin: str = ""  # moscow / china
    carrier: str = ""  # cdek / rupost / cainiao / airfreight


class DeviceCallback(CallbackData, prefix="device"):
    """设备支持."""

    action: str  # menu / serial / issue / more / type / submit
    section: str = ""  # serial / issue / more
    issue_type: str = ""  # firmware / hardware / software / remote


class SupportCallback(CallbackData, prefix="support"):
    """客服合作."""

    action: str  # blogger / wholesaler / huntclub


class NavCallback(CallbackData, prefix="nav"):
    """导航（返回按钮）."""

    action: str  # back / home
    target: str = ""  # 返回目标


# ── 新模块 Callbacks ──────────────────────────────────

class InventoryCallback(CallbackData, prefix="inv"):
    """莫斯科现货查询."""

    action: str  # menu / public_query / vip_enter_password / category / show
    cat_id: str = ""   # 品类 key (如 "outdoor")
    vip: bool = False  # 是否 VIP 完整视图
    page: int = 1


class ServiceCenterCallback(CallbackData, prefix="sc"):
    """A-BF 俄罗斯服务中心."""

    action: str  # menu / info / link / repair / admin_enter / admin_menu / sn_list
    cdek_no: str = ""


class VipCallback(CallbackData, prefix="vip"):
    """Vandych VIP 隐藏菜单."""

    action: str  # menu / discount / sku_select / shipping / wholesale
    sku_idx: int = -1  # 折扣 SKU 列表索引（-1 表示未选择）
