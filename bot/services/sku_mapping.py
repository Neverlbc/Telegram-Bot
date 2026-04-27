"""SKU mapping between Jushuitan and Kuayunbao.

Most products use the same SKU in both systems. A small set has different
codes, and the Google Sheet may contain either side's code. This module keeps
that exception list in one place and gives callers the right query code for
each external system while preserving the original sheet SKU for write-back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


ServiceName = Literal["jst", "kyb"]


@dataclass(frozen=True)
class SkuLookup:
    """Resolved SKU candidates for one sheet SKU."""

    sheet_sku: str
    jst_skus: tuple[str, ...]
    kyb_skus: tuple[str, ...]

    @property
    def is_mapped(self) -> bool:
        """Whether this SKU uses a non-default cross-system mapping."""
        return self.jst_skus != (self.sheet_sku,) or self.kyb_skus != (self.sheet_sku,)


# Each row is: (Jushuitan codes, KYB codes).
# Some source spreadsheets render/copy "+" as "十", so both forms are accepted.
_SKU_GROUPS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("D28720",), ("D28720-A9",)),
    (("DCB203-A9",), ("DCB203",)),
    (("DCH133-NT",), ("DCH133NT",)),
    (("T2S+", "T2S十"), ("T2SPLUS",)),
    (("SS-331H-B001",), ("SS-331H-B001",)),
    (("UT61E+", "UT61E十"), ("UT61EPLUS",)),
    (("F17BMAX-01",), ("17BMAX-01",)),
    (("T2S+FSYZJ", "T2S十FSYZJ"), ("T2SPLUS-FSYZJ",)),
    (("Jerry-YM2.0",), ("JERRY-YM-V2",)),
    (("PFN640+V2", "PFN640十V2"), ("PFN640-V2",)),
    (("UTi260B+", "UTi260B十"), ("UTi260BPLUS",)),
    (("UTi165B+", "UTi165B十"), ("UTi165BPLUS",)),
    (("T2SPRO-SET",), ("T2SPLUS-03",)),
    (("GBA18V5.0AH-GAL18V-40",), ("GBA18V5AH-GAL18V-40",)),
    (("XS06-35LRF-2.0",), ("XS06-35LRF-V2",)),
    (("XS03-35LRF",), ("XS03-35LRF-2AM03-DC",)),
)

_SKU_INDEX: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
for _jst_skus, _kyb_skus in _SKU_GROUPS:
    for _sku in (*_jst_skus, *_kyb_skus):
        _SKU_INDEX[_sku] = (_jst_skus, _kyb_skus)


def resolve_sku(sheet_sku: str) -> SkuLookup:
    """Resolve a sheet SKU to the codes used by each external system."""
    sku = sheet_sku.strip()
    group = _SKU_INDEX.get(sku)
    if not group:
        return SkuLookup(sheet_sku=sku, jst_skus=(sku,), kyb_skus=(sku,))

    jst_skus, kyb_skus = group
    return SkuLookup(sheet_sku=sku, jst_skus=jst_skus, kyb_skus=kyb_skus)


def resolve_skus(sheet_skus: Iterable[str]) -> dict[str, SkuLookup]:
    """Resolve all sheet SKUs, keyed by the original sheet SKU."""
    return {sku: resolve_sku(sku) for sku in sheet_skus}


def service_query_skus(lookups: Iterable[SkuLookup], service: ServiceName) -> list[str]:
    """Return deduplicated query SKUs for one external service."""
    seen: set[str] = set()
    result: list[str] = []
    for lookup in lookups:
        candidates = lookup.jst_skus if service == "jst" else lookup.kyb_skus
        for sku in candidates:
            if sku not in seen:
                seen.add(sku)
                result.append(sku)
    return result


def get_stock_qty(stock_map: dict[str, int], candidates: Iterable[str]) -> int:
    """Read the first available stock value from a service result map."""
    for sku in candidates:
        if sku in stock_map:
            return int(stock_map[sku])
    return 0


def has_stock_record(stock_map: dict[str, int], candidates: Iterable[str]) -> bool:
    """Whether a service result map contains any candidate SKU."""
    return any(sku in stock_map for sku in candidates)
