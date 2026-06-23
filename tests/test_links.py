from __future__ import annotations

from leader_app.links import markdown_name_link, xueqiu_stock_url, xueqiu_symbol


def test_xueqiu_symbol_for_a_share_codes() -> None:
    assert xueqiu_symbol("688981.SH") == "SH688981"
    assert xueqiu_symbol("300033.SZ") == "SZ300033"
    assert xueqiu_symbol("430047.BJ") == "BJ430047"


def test_xueqiu_stock_url_rejects_unknown_codes() -> None:
    assert xueqiu_stock_url("688981.SH") == "https://xueqiu.com/S/SH688981"
    assert xueqiu_stock_url("00700.HK") == ""
    assert xueqiu_stock_url("") == ""


def test_markdown_name_link_uses_stock_name() -> None:
    assert markdown_name_link("688981.SH", "中芯国际") == "[中芯国际](https://xueqiu.com/S/SH688981)"
