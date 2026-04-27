"""Outdoor 库存特殊 SKU 映射表.

左侧为聚水潭 SKU，右侧为 KYB SKU。
Google Sheet 中 SKU 可能使用任一侧编码；同步时：
- 聚水潭使用左侧 SKU 查询 order_lock
- KYB 使用右侧 SKU 查询 tocUsableQty
"""

from __future__ import annotations

SKU_ALIAS_PAIRS: tuple[tuple[str, str], ...] = (
    ("D28720", "D28720-A9"),
    ("DCB203-A9", "DCB203"),
    ("DCH133-NT", "DCH133NT"),
    ("T2S十", "T2SPLUS"),
    ("SS-331H-B001", "SS-331H-B001"),
    ("UT61E十", "UT61EPLUS"),
    ("F17BMAX-01", "17BMAX-01"),
    ("T2S十FSYZJ", "T2SPLUS-FSYZJ"),
    ("Jerry-YM2.0", "JERRY-YM-V2"),
    ("PFN640十V2", "PFN640-V2"),
    ("UTi260B十", "UTi260BPLUS"),
    ("UTi165B十", "UTi165BPLUS"),
    ("T2SPRO-SET", "T2SPLUS-03"),
    ("GBA18V5.0AH-GAL18V-40", "GBA18V5AH-GAL18V-40"),
    ("XS06-35LRF-2.0", "XS06-35LRF-V2"),
    ("XS03-35LRF", "XS03-35LRF-2AM03-DC"),
)


def _jst_ten_key_variants(jst_sku: str) -> list[str]:
    if "十" not in jst_sku:
        return []

    compact = jst_sku.replace("十", "+")
    spaced = jst_sku.replace("十", " + ").strip()
    return list(dict.fromkeys(value for value in (compact, spaced) if value))


def _build_default_aliases() -> dict[str, dict[str, list[str]]]:
    aliases: dict[str, dict[str, list[str]]] = {}
    for jst_sku, kyb_sku in SKU_ALIAS_PAIRS:
        source_aliases = {
            "kyb": [kyb_sku],
            "jst": [jst_sku],
        }
        for sku in (kyb_sku, jst_sku, *_jst_ten_key_variants(jst_sku)):
            aliases[sku] = source_aliases
    return aliases


DEFAULT_SKU_ALIASES: dict[str, dict[str, list[str]]] = _build_default_aliases()
