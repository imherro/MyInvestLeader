from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import get_tushare_token


@dataclass(frozen=True)
class PricePoint:
    code: str
    close: float | None
    pct_chg: float | None
    source: str
    error: str | None = None
    amount: float | None = None
    r5: float | None = None
    r20: float | None = None
    amount_rank: float | None = None
    r1_rank: float | None = None
    r5_rank: float | None = None
    r20_rank: float | None = None
    unit_nav: float | None = None
    premium_rate: float | None = None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_tushare_fund_prices(codes: list[str], basis_date: str) -> dict[str, PricePoint]:
    if not codes:
        return {}
    token = get_tushare_token()
    if not token:
        return {
            code: PricePoint(code=code, close=None, pct_chg=None, source="unavailable", error="missing Tushare token")
            for code in codes
        }
    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api(token)
    except Exception as exc:  # pragma: no cover - runtime dependency
        return {
            code: PricePoint(code=code, close=None, pct_chg=None, source="unavailable", error=f"{type(exc).__name__}: {exc}")
            for code in codes
        }

    trade_date = basis_date.replace("-", "")
    result: dict[str, PricePoint] = {}
    for code in codes:
        try:
            daily = pro.fund_daily(ts_code=code, trade_date=trade_date)
            if daily is None or daily.empty:
                result[code] = PricePoint(code=code, close=None, pct_chg=None, source="Tushare.fund_daily", error="empty")
                continue
            row = daily.iloc[0]
            close = safe_float(row.get("close"))
            unit_nav = _fetch_fund_nav(pro, code, trade_date)
            result[code] = PricePoint(
                code=code,
                close=close,
                pct_chg=safe_float(row.get("pct_chg")),
                source="Tushare.fund_daily" + ("+fund_nav" if unit_nav is not None else ""),
                amount=safe_float(row.get("amount")),
                unit_nav=unit_nav,
                premium_rate=_premium_rate(close, unit_nav),
            )
        except Exception as exc:  # pragma: no cover - external API
            result[code] = PricePoint(code=code, close=None, pct_chg=None, source="Tushare.fund_daily", error=f"{type(exc).__name__}: {exc}")
    return result


def _fetch_fund_nav(pro: Any, code: str, trade_date: str) -> float | None:
    try:
        nav = pro.fund_nav(ts_code=code, end_date=trade_date)
    except Exception:
        return None
    if nav is None or nav.empty:
        return None
    row = nav.iloc[0]
    nav_date = str(row.get("end_date") or row.get("nav_date") or "")
    if nav_date and nav_date.replace("-", "") != trade_date:
        return None
    return safe_float(row.get("unit_nav"))


def _premium_rate(close: float | None, unit_nav: float | None) -> float | None:
    if close is None or unit_nav is None or unit_nav <= 0:
        return None
    return (close / unit_nav - 1.0) * 100.0
