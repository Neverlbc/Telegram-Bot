"""Outdoor price query service backed by the OUTDOOR Google Sheet."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from bot.config import settings
from bot.services.inventory_tiers import inventory_price_currency_keys

logger = logging.getLogger(__name__)

PRICE_OVERVIEW_TITLE = "Brand Price Overview"


@dataclass
class OutdoorPriceItem:
    sku: str
    image_url: str = ""
    description: str = ""
    moscow_stock: str = ""
    status: str = ""
    info: str = ""
    prices: dict[str, str] | None = None


def _get_gspread_client() -> Any:
    import functools
    import gspread
    from google.oauth2.service_account import Credentials

    creds_file = settings.google_credentials_file
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    client = gspread.authorize(creds)
    if hasattr(client, "auth") and callable(getattr(client.auth, "request", None)):
        client.auth.request = functools.partial(client.auth.request, timeout=60)
    return client


def _normalize_title(value: str) -> str:
    return (value or "").replace(" ", "").replace("[", "【").replace("]", "】").strip().casefold()


def _is_stock_title(title: str) -> bool:
    normalized = _normalize_title(title)
    return normalized.startswith("stock_outdoor") or normalized.startswith("stockoutdoor")


def _is_price_overview_title(title: str) -> bool:
    return _normalize_title(title) == _normalize_title(PRICE_OVERVIEW_TITLE)


def _open_spreadsheet() -> Any:
    if not settings.outdoor_sheet_id:
        raise ValueError("OUTDOOR_SHEET_ID 未配置")
    return _get_gspread_client().open_by_key(settings.outdoor_sheet_id)


def _price_brand_titles_sync() -> list[str]:
    spreadsheet = _open_spreadsheet()
    titles: list[str] = []
    for worksheet in spreadsheet.worksheets():
        title = worksheet.title.strip()
        if not title or _is_stock_title(title) or _is_price_overview_title(title):
            continue
        titles.append(title)
    return titles


def _exchange_rate_sync() -> str:
    spreadsheet = _open_spreadsheet()
    return _extract_exchange_rate(_overview_values(spreadsheet))


def _find_worksheet(spreadsheet: Any, title: str) -> Any | None:
    expected = _normalize_title(title)
    for worksheet in spreadsheet.worksheets():
        if _normalize_title(worksheet.title) == expected:
            return worksheet
    return None


def _overview_values(spreadsheet: Any) -> list[list[str]]:
    worksheet = _find_worksheet(spreadsheet, PRICE_OVERVIEW_TITLE)
    if worksheet is None:
        return []
    return worksheet.get_all_values()


def _sku_key(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().casefold()


def _extract_exchange_rate(values: list[list[str]]) -> str:
    for row_idx, row in enumerate(values):
        for col_idx, cell in enumerate(row):
            label = " ".join((cell or "").split()).casefold()
            if "统一汇率" not in label and "汇率" not in label:
                continue
            candidates: list[str] = []
            if row_idx + 1 < len(values) and col_idx < len(values[row_idx + 1]):
                candidates.append(values[row_idx + 1][col_idx])
            if col_idx + 1 < len(row):
                candidates.append(row[col_idx + 1])
            for candidate in candidates:
                rate = _first_number(candidate)
                if rate:
                    return rate
    if len(values) > 1 and len(values[1]) > 10:
        return _first_number(values[1][10])
    return ""


def _first_number(value: str) -> str:
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return match.group(0).replace(",", ".") if match else ""


def _normalized_cell(value: str) -> str:
    return " ".join((value or "").strip().split()).casefold()


def _find_header_row(values: list[list[str]]) -> int:
    for idx, row in enumerate(values[:12]):
        normalized = [_normalized_cell(cell) for cell in row]
        if any("sku" in cell for cell in normalized):
            return idx
    for idx, row in enumerate(values[:12]):
        if sum(1 for cell in row if str(cell).strip()) >= 2:
            return idx
    return 0


def _combined_headers(values: list[list[str]], header_idx: int) -> list[str]:
    """Combine the SKU header row with nearby merged/section header rows."""
    rows = values[max(0, header_idx - 3) : header_idx + 1]
    width = max((len(row) for row in rows), default=0)
    filled_rows: list[list[str]] = []
    for row in rows:
        filled: list[str] = []
        last = ""
        for col_idx in range(width):
            value = row[col_idx].strip() if col_idx < len(row) else ""
            if value:
                last = value
            filled.append(last)
        filled_rows.append(filled)

    headers: list[str] = []
    for col_idx in range(width):
        parts: list[str] = []
        for row in filled_rows:
            value = row[col_idx].strip()
            if value and value not in parts:
                parts.append(value)
        headers.append(" ".join(parts))
    return headers


def _overview_tier_price_map(values: list[list[str]], tier: str) -> dict[str, str]:
    """Read USD prices from Brand Price Overview by SKU for the given tier."""
    if not values:
        return {}

    header_idx = _find_header_row(values)
    headers = _combined_headers(values, header_idx)
    roles = _column_roles(headers)
    sku_idx = roles.get("sku", 0)
    price_idx = roles.get(f"{tier}_usd")
    if price_idx is None:
        price_idx = roles.get(f"{tier}_plain")
    if price_idx is None:
        price_idx = roles.get(tier)
    if price_idx is None:
        return {}

    prices: dict[str, str] = {}
    for row in values[header_idx + 1:]:
        padded = [*row, "", "", "", "", "", ""]
        sku = padded[sku_idx].strip() if sku_idx < len(padded) else ""
        price = padded[price_idx].strip() if price_idx < len(padded) else ""
        if sku and price:
            prices[_sku_key(sku)] = price
    return prices


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _is_russia_address_header(value: str) -> bool:
    return _contains_any(
        value,
        (
            "俄罗斯地址",
            "俄地址",
            "俄罗斯",
            "russia address",
            "russian address",
            "ru address",
            "россий",
            "россия",
            "русск",
        ),
    )


def _is_china_address_header(value: str) -> bool:
    return _contains_any(
        value,
        (
            "中国地址",
            "国内地址",
            "中国",
            "china address",
            "chinese address",
            "cn address",
            "китай",
        ),
    )


def _has_tier_marker(value: str, tier: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(tier)}(?![a-z0-9])", value) is not None


def _set_cny_role(roles: dict[str, int], key_prefix: str, text: str, idx: int) -> None:
    prefix = f"{key_prefix}_" if key_prefix else ""
    if _is_russia_address_header(text) and f"{prefix}cny_ru" not in roles:
        roles[f"{prefix}cny_ru"] = idx
    elif _is_china_address_header(text) and f"{prefix}cny_cn" not in roles:
        roles[f"{prefix}cny_cn"] = idx
    if f"{prefix}cny" not in roles:
        roles[f"{prefix}cny"] = idx


def _column_roles(headers: list[str]) -> dict[str, int]:
    roles: dict[str, int] = {}
    for idx, header in enumerate(headers):
        text = _normalized_cell(header)
        is_rub = _contains_any(text, ("руб", "ruble", "рубл", "卢布", "aliexpress"))
        is_cny = _contains_any(text, ("юань", "yuan", "rmb", "cny", "人民币"))
        is_usd = _contains_any(text, ("usd", "дол", "美元", "dollar", "$"))
        for tier in ("vvip", "svip", "vip"):
            if not _has_tier_marker(text, tier):
                continue
            if is_usd and f"{tier}_usd" not in roles:
                roles[f"{tier}_usd"] = idx
            if is_rub and f"{tier}_rub" not in roles:
                roles[f"{tier}_rub"] = idx
            if is_cny:
                _set_cny_role(roles, tier, text, idx)
            if not (is_usd or is_rub or is_cny) and f"{tier}_plain" not in roles:
                roles[f"{tier}_plain"] = idx
        if "sku" in text and "sku" not in roles:
            roles["sku"] = idx
        if _contains_any(text, ("图片", "image", "photo", "pic", "фото", "изображ", "картин")) and "image" not in roles:
            roles["image"] = idx
        if _contains_any(text, ("描述", "description", "describe", "описывать", "опис")) and "description" not in roles:
            roles["description"] = idx
        if (
            _contains_any(text, ("московский склад", "moscow stock", "moscow warehouse", "莫斯科库存", "莫仓库存"))
            and "moscow_stock" not in roles
        ):
            roles["moscow_stock"] = idx
        if _contains_any(text, ("状态", "state", "status", "состояние")) and "status" not in roles:
            roles["status"] = idx
        if is_rub and "rub" not in roles:
            roles["rub"] = idx
        if is_cny:
            _set_cny_role(roles, "", text, idx)
        if is_usd and "usd" not in roles:
            roles["usd"] = idx
    roles.setdefault("sku", 0)
    return roles


def _price_role_candidates(tier: str, key: str) -> tuple[str, ...]:
    if key == "cny_ru":
        return (f"{tier}_cny_ru", "cny_ru")
    if key == "cny_cn":
        return (f"{tier}_cny_cn", "cny_cn")
    return (f"{tier}_{key}", key)


def _price_column_index(roles: dict[str, int], tier: str, key: str) -> int | None:
    for role in _price_role_candidates(tier, key):
        if role in roles:
            return roles[role]
    return None


def _looks_like_url(value: str) -> bool:
    text = (value or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def _extract_image_url(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if _looks_like_url(text):
        return text
    match = re.search(r"https?://[^\"')\s,;]+", text, re.I)
    return match.group(0) if match else ""


def _pick_image_url(row: list[str], roles: dict[str, int], formula_row: list[str] | None = None) -> str:
    image_idx = roles.get("image")
    formula_row = formula_row or []
    candidates: list[str] = []
    if image_idx is not None:
        if image_idx < len(row):
            candidates.append(row[image_idx])
        if image_idx < len(formula_row):
            candidates.append(formula_row[image_idx])
    candidates.extend(row)
    candidates.extend(formula_row)
    for value in candidates:
        url = _extract_image_url(value)
        if url:
            return url
    return ""


def _pick_role_value(row: list[str], roles: dict[str, int], role: str) -> str:
    idx = roles.get(role)
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def _row_info(headers: list[str], row: list[str], roles: dict[str, int]) -> str:
    skipped = {idx for idx in roles.values()}
    parts: list[str] = []
    for idx, value in enumerate(row):
        value = (value or "").strip()
        if not value or idx in skipped or _looks_like_url(value):
            continue
        header = headers[idx].strip() if idx < len(headers) and headers[idx].strip() else f"字段{idx + 1}"
        parts.append(f"{header}: {value}")
        if len(parts) >= 4:
            break
    return "；".join(parts)


def _price_items_sync(brand_title: str, tier: str) -> tuple[list[OutdoorPriceItem], str]:
    spreadsheet = _open_spreadsheet()
    worksheet = _find_worksheet(spreadsheet, brand_title)
    if worksheet is None:
        raise ValueError(f"找不到价格表 tab: {brand_title}")

    overview_values = _overview_values(spreadsheet)
    exchange_rate = _extract_exchange_rate(overview_values)
    values = worksheet.get_all_values()
    if not values:
        return [], exchange_rate
    formula_values = worksheet.get_all_values(value_render_option="FORMULA")

    header_idx = _find_header_row(values)
    headers = _combined_headers(values, header_idx)
    roles = _column_roles(headers)
    wanted_prices = inventory_price_currency_keys(tier)
    overview_usd_prices = _overview_tier_price_map(overview_values, tier) if "usd" in wanted_prices else {}

    items: list[OutdoorPriceItem] = []
    for row_idx, row in enumerate(values[header_idx + 1:], start=header_idx + 1):
        padded = [*row, "", "", "", "", "", ""]
        formula_row = formula_values[row_idx] if row_idx < len(formula_values) else []
        padded_formula = [*formula_row, "", "", "", "", "", ""]
        sku_idx = roles.get("sku", 0)
        sku = padded[sku_idx].strip() if sku_idx < len(padded) else ""
        if not sku:
            continue

        prices: dict[str, str] = {}
        for key in wanted_prices:
            value = ""
            if key == "usd":
                value = overview_usd_prices.get(_sku_key(sku), "")
            if not value:
                col_idx = _price_column_index(roles, tier, key)
                if col_idx is not None and col_idx < len(padded):
                    value = padded[col_idx].strip()
            if value:
                prices[key] = value

        items.append(
            OutdoorPriceItem(
                sku=sku,
                image_url=_pick_image_url(padded, roles, padded_formula),
                description=_pick_role_value(padded, roles, "description"),
                moscow_stock=_pick_role_value(padded, roles, "moscow_stock"),
                status=_pick_role_value(padded, roles, "status"),
                info=_row_info(headers, padded, roles),
                prices=prices,
            )
        )

    return items, exchange_rate


async def get_outdoor_price_brand_titles() -> list[str]:
    try:
        return await asyncio.to_thread(_price_brand_titles_sync)
    except Exception as exc:
        logger.warning("get outdoor price brand titles failed: %s", exc)
        return []


async def get_outdoor_exchange_rate() -> str:
    try:
        return await asyncio.to_thread(_exchange_rate_sync)
    except Exception as exc:
        logger.warning("get outdoor exchange rate failed: %s", exc)
        return ""


async def get_outdoor_price_items(brand_title: str, tier: str) -> tuple[list[OutdoorPriceItem], str]:
    try:
        return await asyncio.to_thread(_price_items_sync, brand_title, tier)
    except Exception as exc:
        logger.warning("get outdoor price items failed: %s", exc)
        return [], ""
