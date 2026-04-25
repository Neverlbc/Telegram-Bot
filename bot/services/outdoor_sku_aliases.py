"""Outdoor 库存特殊 SKU 映射表.

左侧为 KYB SKU，右侧为聚水潭 SKU。
Google Sheet 中 SKU 默认使用 KYB SKU；同步时：
- KYB 使用左侧 SKU 查询 tocUsableQty
- 聚水潭使用右侧 SKU 查询 order_lock
"""

from __future__ import annotations

SKU_ALIAS_PAIRS: tuple[tuple[str, str], ...] = (
    ("DCB203", "DCB203-A9"),
    ("DCH133NT", "DCH133-NT"),
    ("T2SPLUS", "T2S十"),
    ("SS-331H-B001", "SS-331H-B001"),
    ("UT61EPLUS", "UT61E十"),
    ("17BMAX-01", "F17BMAX-01"),
    ("T2SPLUS-FSYZJ", "T2S十FSYZJ"),
    ("JERRY-YM-V2", "Jerry-YM2.0"),
    ("PFN640-V2", "PFN640十V2"),
    ("UTi260BPLUS", "UTi260B十"),
    ("UTi165BPLUS", "UTi165B十"),
    ("T2SPLUS-03", "T2SPRO-SET"),
    ("GBA18V5AH-GAL18V-40", "GBA18V5.0AH-GAL18V-40"),
    ("XS06-35LRF-V2", "XS06-35LRF-2.0"),
    ("XS03-35LRF-2AM03-DC", "XS03-35LRF"),
)

def _build_default_aliases() -> dict[str, dict[str, list[str]]]:
    aliases: dict[str, dict[str, list[str]]] = {}
    for kyb_sku, jst_sku in SKU_ALIAS_PAIRS:
        source_aliases = {
            "kyb": [kyb_sku],
            "jst": [jst_sku],
        }
        aliases[kyb_sku] = source_aliases
        aliases[jst_sku] = source_aliases
    return aliases


DEFAULT_SKU_ALIASES: dict[str, dict[str, list[str]]] = _build_default_aliases()
