"""RHP guide price data from the outdoor Google Sheet."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from bot.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RHPGuidePriceItem:
    sku: str
    guide_price: str
    brand: str = ""


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


def _worksheet_gid(worksheet: Any) -> int | None:
    for attr in ("id", "gid"):
        value = getattr(worksheet, attr, None)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _find_worksheet_by_gid(spreadsheet: Any, gid: int) -> Any | None:
    getter = getattr(spreadsheet, "get_worksheet_by_id", None)
    if callable(getter):
        try:
            worksheet = getter(gid)
            if worksheet is not None:
                return worksheet
        except Exception:
            logger.debug("get_worksheet_by_id failed for gid=%s", gid, exc_info=True)

    for worksheet in spreadsheet.worksheets():
        if _worksheet_gid(worksheet) == gid:
            return worksheet
    return None


def _first_number(value: str) -> str:
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return match.group(0).replace(",", ".") if match else ""


def _looks_like_sku(value: str) -> bool:
    text = (value or "").strip()
    return bool(re.search(r"\d", text) and re.search(r"[A-Za-z]", text))


def _parse_guide_prices(values: list[list[str]]) -> list[RHPGuidePriceItem]:
    items: list[RHPGuidePriceItem] = []
    current_brand = ""
    seen: set[tuple[str, str]] = set()

    for row in values:
        sku = row[0].strip() if row else ""
        guide_price = row[1].strip() if len(row) > 1 else ""
        if not sku:
            continue

        normalized = " ".join(sku.split()).casefold()
        if normalized in {"sku", "model", "型号"} or "rhp" in normalized:
            continue
        if "指导价" in guide_price or "guide" in guide_price.casefold():
            continue

        if not _first_number(guide_price):
            if not _looks_like_sku(sku):
                current_brand = sku
            continue

        dedupe_key = (sku.casefold(), guide_price)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            RHPGuidePriceItem(
                sku=sku,
                guide_price=guide_price,
                brand=current_brand,
            )
        )

    return items


def _guide_prices_sync() -> list[RHPGuidePriceItem]:
    if not settings.outdoor_sheet_id:
        raise ValueError("OUTDOOR_SHEET_ID is not configured")

    spreadsheet = _get_gspread_client().open_by_key(settings.outdoor_sheet_id)
    worksheet = _find_worksheet_by_gid(spreadsheet, settings.rhp_guide_sheet_gid)
    if worksheet is None:
        raise ValueError(f"RHP guide price sheet gid={settings.rhp_guide_sheet_gid} not found")
    return _parse_guide_prices(worksheet.get_all_values())


async def get_rhp_guide_prices() -> list[RHPGuidePriceItem]:
    try:
        return await asyncio.to_thread(_guide_prices_sync)
    except Exception as exc:
        logger.warning("get RHP guide prices failed: %s", exc)
        return []
