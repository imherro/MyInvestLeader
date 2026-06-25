from __future__ import annotations

from pathlib import Path


def test_template_embeds_unified_header_and_footer() -> None:
    html = Path("templates/index.html").read_text(encoding="utf-8")

    assert "<div data-myinvest-header></div>" in html
    assert "<div data-myinvest-footer></div>" in html
    assert 'src="https://invest.okbbc.com/header.js"' in html
    assert 'src="https://invest.okbbc.com/footer.js"' in html
    assert 'data-target="[data-myinvest-header]"' in html
    assert 'data-target="[data-myinvest-footer]"' in html
    assert 'class="app-title"' in html
    assert "A股主线龙头研究与影子仓位接口" in html
