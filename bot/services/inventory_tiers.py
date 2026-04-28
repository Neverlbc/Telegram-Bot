"""Inventory permission tiers."""

from __future__ import annotations

from dataclasses import dataclass

from bot.services.hidden_access import MENU_SVIP_INVENTORY, MENU_VIP_INVENTORY, MENU_VVIP_INVENTORY

PUBLIC_TIER = "public"
VIP_TIER = "vip"
SVIP_TIER = "svip"
VVIP_TIER = "vvip"


@dataclass(frozen=True)
class InventoryTier:
    code: str
    label: str
    access_key: str
    stock_sheet_title: str
    price_currency_keys: tuple[str, ...]


INVENTORY_TIERS: dict[str, InventoryTier] = {
    VIP_TIER: InventoryTier(
        code=VIP_TIER,
        label="VIP",
        access_key=MENU_VIP_INVENTORY,
        stock_sheet_title="Stock_Outdoor 【VIP版】",
        price_currency_keys=("rub",),
    ),
    SVIP_TIER: InventoryTier(
        code=SVIP_TIER,
        label="SVIP",
        access_key=MENU_SVIP_INVENTORY,
        stock_sheet_title="Stock_Outdoor 【SVIP版】",
        price_currency_keys=("rub", "cny_ru", "cny_cn"),
    ),
    VVIP_TIER: InventoryTier(
        code=VVIP_TIER,
        label="VVIP",
        access_key=MENU_VVIP_INVENTORY,
        stock_sheet_title="Stock_Outdoor 【VVIP版】",
        price_currency_keys=("usd", "rub", "cny_ru", "cny_cn"),
    ),
}

PUBLIC_STOCK_SHEET_TITLE = "Stock_Outdoor 【普通版】"
PRICE_TIER_CODES = tuple(INVENTORY_TIERS)


def normalize_inventory_tier(tier: str | None = None, vip: bool = False) -> str:
    code = (tier or "").strip().lower()
    if code in INVENTORY_TIERS:
        return code
    return VIP_TIER if vip else PUBLIC_TIER


def is_price_tier(tier: str | None) -> bool:
    return normalize_inventory_tier(tier) in INVENTORY_TIERS


def inventory_tier_label(tier: str | None) -> str:
    code = normalize_inventory_tier(tier)
    if code == PUBLIC_TIER:
        return "普通"
    return INVENTORY_TIERS[code].label


def inventory_tier_access_key(tier: str | None) -> str:
    code = normalize_inventory_tier(tier)
    if code == PUBLIC_TIER:
        return ""
    return INVENTORY_TIERS[code].access_key


def inventory_stock_sheet_title(tier: str | None) -> str:
    code = normalize_inventory_tier(tier)
    if code == PUBLIC_TIER:
        return PUBLIC_STOCK_SHEET_TITLE
    return INVENTORY_TIERS[code].stock_sheet_title


def inventory_price_currency_keys(tier: str | None) -> tuple[str, ...]:
    code = normalize_inventory_tier(tier)
    if code == PUBLIC_TIER:
        return ()
    return INVENTORY_TIERS[code].price_currency_keys
