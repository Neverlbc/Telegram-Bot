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
    info: str = ""
    prices: dict[str, str] | None = None


def _get_gspread_client() -> Any:
    import gspread
    from google.oauth2.service_account import Credentials

    creds_file = settings.google_credentials_file
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
    return gspread.authorize(creds)


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


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _column_roles(headers: list[str]) -> dict[str, int]:
    roles: dict[str, int] = {}
    for idx, header in enumerate(headers):
        text = _normalized_cell(header)
        if "vvip" in text and "vvip_rub" not in roles:
            roles["vvip_rub"] = idx
        elif "svip" in text and "svip_rub" not in roles:
            roles["svip_rub"] = idx
        elif "vip" in text and "vip_rub" not in roles:
            roles["vip_rub"] = idx
        if "sku" in text and "sku" not in roles:
            roles["sku"] = idx
        if _contains_any(text, ("图片", "image", "photo", "pic", "фото", "изображ", "картин")) and "image" not in roles:
            roles["image"] = idx
        if _contains_any(text, ("руб", "ruble", "рубл", "卢布", "aliexpress")) and "rub" not in roles:
            roles["rub"] = idx
        if _contains_any(text, ("юань", "yuan", "rmb", "cny", "人民币")) and "cny" not in roles:
            roles["cny"] = idx
        if _contains_any(text, ("usd", "дол", "美元", "dollar", "$")) and "usd" not in roles:
            roles["usd"] = idx
    roles.setdefault("sku", 0)
    return roles


def _looks_like_url(value: str) -> bool:
    text = (value or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def _pick_image_url(row: list[str], roles: dict[str, int]) -> str:
    image_idx = roles.get("image")
    if image_idx is not None and image_idx < len(row) and _looks_like_url(row[image_idx]):
        return row[image_idx].strip()
    for value in row:
        if _looks_like_url(value) and re.search(r"\.(?:jpg|jpeg|png|webp)(?:\?|$)", value, re.I):
            return value.strip()
    return ""


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

    exchange_rate = _extract_exchange_rate(_overview_values(spreadsheet))
    values = worksheet.get_all_values()
    if not values:
        return [], exchange_rate

    header_idx = _find_header_row(values)
    headers = values[header_idx]
    roles = _column_roles(headers)
    wanted_prices = inventory_price_currency_keys(tier)
    price_labels = {"usd": "美元价格", "rub": "卢布价格", "cny": "人民币价格"}
    rub_role = f"{tier}_rub"

    items: list[OutdoorPriceItem] = []
    for row in values[header_idx + 1:]:
        padded = [*row, "", "", "", "", "", ""]
        sku_idx = roles.get("sku", 0)
        sku = padded[sku_idx].strip() if sku_idx < len(padded) else ""
        if not sku:
            continue

        prices: dict[str, str] = {}
        for key in wanted_prices:
            if key == "rub":
                col_idx = roles.get(rub_role, roles.get("rub"))
            else:
                col_idx = roles.get(key)
            value = ""
            if col_idx is not None and col_idx < len(padded):
                value = padded[col_idx].strip()
            if value:
                prices[price_labels[key]] = value

        items.append(
            OutdoorPriceItem(
                sku=sku,
                image_url=_pick_image_url(padded, roles),
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
