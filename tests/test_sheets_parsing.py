"""Google Sheets CSV parsing tests."""

from __future__ import annotations


def test_internal_sheet_skips_group_titles() -> None:
    """Internal inventory sheets contain visual group rows that are not SKUs."""
    from bot.services.sheets import _parse_csv

    csv_text = "SKU,QTYS,在途库存\nSytong,,\nMM06-50LRF,,\nAir Soft,,\nT2MINI,,\n"

    items = _parse_csv(csv_text, "thermal_internal")

    assert [item.sku for item in items] == ["MM06-50LRF", "T2MINI"]
    assert [item.qty for item in items] == [0, 0]


def test_public_sheet_keeps_existing_layout() -> None:
    """Public Bot inventory sheets still parse the old SKU/QTYS/State/Notes layout."""
    from bot.services.sheets import _parse_csv

    csv_text = "SKU,QTYS,State,Notes\nD28720,3,Available,\n"

    items = _parse_csv(csv_text, "thermal_industrial")

    assert len(items) == 1
    assert items[0].sku == "D28720"
    assert items[0].qty == 3


def test_stock_state_and_notes_rules() -> None:
    """Stock sync updates State/Notes while preserving manual notes."""
    from bot.services.sheets import OUT_OF_STOCK_NOTE, notes_for_stock, state_for_stock

    assert state_for_stock(0) == "None"
    assert notes_for_stock(0, "manual") == OUT_OF_STOCK_NOTE

    assert state_for_stock(5) == "有货"
    assert notes_for_stock(5, "在途中") == ""
    assert notes_for_stock(5, "在途中；保留这个备注") == "保留这个备注"
    assert notes_for_stock(5, "保留这个备注，在途中") == "保留这个备注"
    assert notes_for_stock(5, "None") == ""
    assert notes_for_stock(5, OUT_OF_STOCK_NOTE) == ""
    assert notes_for_stock(5, "保留这个备注") == "保留这个备注"
