"""SN 序列号查询服务 — 跨品牌 tab 搜索设备序列号."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)

SHEETS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d"
    "/{sheet_id}/export?format=csv&gid={gid}"
)

# 品牌 tab 配置: (品牌显示名, GID)
SN_TABS: list[tuple[str, int]] = [
    ("Infiray",  921834481),
    ("Sytong",  2050495017),
    ("Longot",  1237524483),
    ("NNPO",     825808586),
    ("Pard",    1890117141),
    ("Airsoft", 1022090635),
    ("DNT",      112980859),
]

COL_SN    = "SN"
COL_NOTES = "Notes"


@dataclass
class SNRecord:
    brand: str
    model: str
    sn: str
    notes: str = ""

    def format_text(self, lang: str = "zh") -> str:
        labels = {
            "zh": ("品牌", "型号", "序列号", "✅ 该设备记录存在"),
            "en": ("Brand", "Model", "Serial No.", "✅ Device record found"),
            "ru": ("Бренд", "Модель", "Серийный номер", "✅ Устройство найдено"),
        }.get(lang, ("品牌", "型号", "序列号", "✅ 该设备记录存在"))

        lines = [
            labels[3],
            "",
            f"<b>{labels[0]}：</b>{self.brand}",
            f"<b>{labels[1]}：</b>{self.model}",
            f"<b>{labels[2]}：</b><code>{self.sn}</code>",
        ]
        if self.notes and self.notes.lower() != "notes":
            lines.append(f"📝 {self.notes}")
        return "\n".join(lines)


async def search_sn(query: str) -> list[SNRecord]:
    """在所有品牌 tab 中搜索 SN（精确匹配，大小写不敏感）."""
    q = query.strip().upper()
    if not q:
        return []

    sheet_id = settings.service_center_sheet_id
    if not sheet_id:
        logger.warning("service_center_sheet_id not configured")
        return []

    results: list[SNRecord] = []
    async with aiohttp.ClientSession() as session:
        for brand, gid in SN_TABS:
            url = SHEETS_CSV_URL.format(sheet_id=sheet_id, gid=gid)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    csv_text = await resp.text(encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to fetch %s SN tab (gid=%d): %s", brand, gid, e)
                continue

            reader = csv.DictReader(io.StringIO(csv_text))
            headers = list(reader.fieldnames or [])
            model_col = headers[0] if headers else ""  # A列 = 型号列，列名因品牌而异

            for row in reader:
                sn_val = row.get(COL_SN, "").strip().upper()
                if sn_val == q:
                    results.append(SNRecord(
                        brand=brand,
                        model=row.get(model_col, "").strip(),
                        sn=row.get(COL_SN, "").strip(),
                        notes=row.get(COL_NOTES, "").strip(),
                    ))

    return results
