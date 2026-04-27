"""CallbackData 单元测试."""

from __future__ import annotations


def test_lang_callback_pack() -> None:
    """测试语言回调数据打包."""
    from bot.keyboards.callbacks import LangCallback

    cb = LangCallback(code="zh")
    packed = cb.pack()
    assert "lang" in packed
    assert "zh" in packed


def test_menu_callback_pack() -> None:
    """测试主菜单回调数据打包."""
    from bot.keyboards.callbacks import MenuCallback

    cb = MenuCallback(action="presale")
    packed = cb.pack()
    assert "menu" in packed
    assert "presale" in packed


def test_nav_callback_pack() -> None:
    """测试导航回调数据打包."""
    from bot.keyboards.callbacks import NavCallback

    cb = NavCallback(action="back", target="menu")
    packed = cb.pack()
    assert "nav" in packed


def test_presale_callback_defaults() -> None:
    """测试售前回调默认值."""
    from bot.keyboards.callbacks import PresaleCallback

    cb = PresaleCallback(action="catalog")
    assert cb.cat_id == ""
    assert cb.page == 1


def test_logistics_callback() -> None:
    """测试物流回调数据."""
    from bot.keyboards.callbacks import LogisticsCallback

    cb = LogisticsCallback(action="origin", origin="moscow")
    packed = cb.pack()
    assert "logistics" in packed
    assert "moscow" in packed
