"""SKU mapping tests."""

from __future__ import annotations


def test_resolve_jst_sku_to_kyb_sku() -> None:
    """A sheet row using the Jushuitan SKU queries KYB with the mapped code."""
    from bot.services.sku_mapping import resolve_sku

    lookup = resolve_sku("D28720")

    assert lookup.jst_skus == ("D28720",)
    assert lookup.kyb_skus == ("D28720-A9",)


def test_resolve_kyb_sku_to_jst_sku() -> None:
    """A sheet row using the KYB SKU still queries Jushuitan with its code."""
    from bot.services.sku_mapping import resolve_sku

    lookup = resolve_sku("D28720-A9")

    assert lookup.jst_skus == ("D28720",)
    assert lookup.kyb_skus == ("D28720-A9",)


def test_resolve_plus_alias_from_sheet() -> None:
    """The copied Chinese ten character is treated as a plus-sign alias."""
    from bot.services.sku_mapping import resolve_sku

    lookup = resolve_sku("T2S十")

    assert lookup.jst_skus == ("T2S+", "T2S十")
    assert lookup.kyb_skus == ("T2SPLUS",)


def test_pfn640_plus_alias_uses_jushuitan_10_code() -> None:
    """PFN640 plus aliases are sheet aliases; Jushuitan must receive the 10 code."""
    from bot.services.sku_mapping import resolve_sku, service_query_skus

    lookups = [
        resolve_sku("PFN640+V2"),
        resolve_sku("PFN640 + V2"),
        resolve_sku("PFN640十V2"),
        resolve_sku("PFN640-V2"),
    ]

    for lookup in lookups:
        assert lookup.jst_skus == ("PFN64010V2",)
        assert lookup.kyb_skus == ("PFN640-V2",)

    assert service_query_skus(lookups, "jst") == ["PFN64010V2"]
    assert service_query_skus(lookups, "kyb") == ["PFN640-V2"]


def test_service_query_skus_deduplicates_mapped_pairs() -> None:
    """If both sides of one pair appear in the sheet, each service is queried once."""
    from bot.services.sku_mapping import resolve_skus, service_query_skus

    lookups = resolve_skus(["D28720", "D28720-A9"])

    assert service_query_skus(lookups.values(), "jst") == ["D28720"]
    assert service_query_skus(lookups.values(), "kyb") == ["D28720-A9"]


def test_get_stock_qty_reads_first_matching_candidate() -> None:
    """Stock values can be read from any candidate code returned by a service."""
    from bot.services.sku_mapping import get_stock_qty

    assert get_stock_qty({"T2S十": 3}, ("T2S+", "T2S十")) == 3
    assert get_stock_qty({}, ("T2S+", "T2S十")) == 0
