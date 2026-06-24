from __future__ import annotations

from pathlib import Path


def test_header_uses_unified_system_navigation() -> None:
    html = Path("templates/index.html").read_text(encoding="utf-8")
    expected_links = [
        ("首页", "https://invest.okbbc.com/"),
        ("市场", "https://market.okbbc.com/"),
        ("主线", "https://theme.okbbc.com/"),
        ("影子", "https://shadow.okbbc.com/"),
        ("龙头", "https://leader.okbbc.com/"),
        ("个股", "https://stock.okbbc.com/"),
        ("操作", "https://position.okbbc.com/"),
    ]

    assert 'aria-label="MyInvest 系统导航"' in html
    for label, href in expected_links:
        assert f'href="{href}"' in html
        assert f">{label}</a>" in html
    assert 'aria-current="page">龙头</a>' in html
