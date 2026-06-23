from __future__ import annotations

import re


XUEQIU_BASE_URL = "https://xueqiu.com/S"
_A_SHARE_CODE_RE = re.compile(r"^(?P<number>\d{6})\.(?P<market>SH|SZ|BJ)$", re.IGNORECASE)


def xueqiu_symbol(code: str | None) -> str:
    match = _A_SHARE_CODE_RE.match(str(code or "").strip())
    if not match:
        return ""
    return f"{match.group('market').upper()}{match.group('number')}"


def xueqiu_stock_url(code: str | None) -> str:
    symbol = xueqiu_symbol(code)
    return f"{XUEQIU_BASE_URL}/{symbol}" if symbol else ""


def markdown_name_link(code: str | None, name: str | None) -> str:
    text = str(name or code or "").strip()
    url = xueqiu_stock_url(code)
    return f"[{text}]({url})" if text and url else text
