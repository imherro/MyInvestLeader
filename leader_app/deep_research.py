from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import ROOT_DIR, STOCK_REPORT_DIR, get_tushare_token
from .pricing import safe_float


TZ = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "stock_deep_research.v1"
SHADOW_SCHEMA_VERSION = "stock_deep_shadow_input.v1"
ACTIVE_THEME_GRADES = {"A", "B"}
ACTIVE_STOCK_GRADES = {"A", "B"}


def _now_report_id() -> str:
    return f"stock_deep_review_{datetime.now(TZ).strftime('%Y-%m-%d_%H%M%S')}"


def _round(value: Any, digits: int = 4) -> float | None:
    number = safe_float(value)
    if number is None or math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _rescale(value: Any, low: float, high: float, fallback: float = 45.0) -> float:
    number = safe_float(value)
    if number is None or high <= low:
        return fallback
    return _clamp((number - low) / (high - low) * 100.0)


def _compact_date(value: str | None) -> str:
    return (value or "").replace("-", "")


def _deep_rating(score: float, *, risk_flags: list[str], data_gaps: list[str]) -> str:
    if any("ST" in item or "退市" in item for item in risk_flags):
        return "C"
    if score >= 82 and len(data_gaps) <= 1:
        return "S"
    if score >= 72:
        return "A"
    if score >= 60:
        return "B"
    return "C"


def _rating_label(rating: str) -> str:
    return {
        "S": "核心确认",
        "A": "可跟踪龙头",
        "B": "观察股",
        "C": "剔除/暂缓",
    }.get(rating, "观察股")


def _safe_mean(values: list[float | None], fallback: float = 45.0) -> float:
    valid = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if not valid:
        return fallback
    return sum(valid) / len(valid)


def select_deep_queue(leader_payload: dict[str, Any], max_per_theme: int = 3) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    priority = 1
    for theme in leader_payload.get("themes") or []:
        theme_grade = theme.get("leader_grade")
        all_stock_rows = list(theme.get("stock_leaders") or [])
        if theme_grade in ACTIVE_THEME_GRADES:
            stock_rows = [row for row in all_stock_rows if row.get("grade") in ACTIVE_STOCK_GRADES]
            queue_reason = "主线分层进入A/B，个股候选进入A/B，进入ResearchFirst深研"
        else:
            stock_rows = [
                row
                for row in all_stock_rows
                if row.get("leader_tier") == "证据确认龙头" and row.get("grade") in ACTIVE_STOCK_GRADES
            ]
            queue_reason = "主线短期未确认，但个股为证据确认龙头，进入ResearchFirst跟踪深研"
        if theme_grade not in ACTIVE_THEME_GRADES and not stock_rows:
            continue
        if not stock_rows:
            stock_rows = all_stock_rows
        for stock in stock_rows[:max_per_theme]:
            queue.append(
                {
                    "priority": priority,
                    "theme": theme.get("theme"),
                    "theme_id": theme.get("theme_id"),
                    "theme_stage": theme.get("stage"),
                    "theme_grade": theme.get("leader_grade"),
                    "theme_score": theme.get("leader_score"),
                    "theme_lifecycle_state": theme.get("lifecycle_state"),
                    "code": stock.get("code"),
                    "name": stock.get("name"),
                    "industry": stock.get("industry"),
                    "candidate_grade": stock.get("grade"),
                    "candidate_leader_score": stock.get("leader_score"),
                    "candidate_pct_chg": stock.get("pct_chg"),
                    "candidate_turnover_rate": stock.get("turnover_rate"),
                    "candidate_is_limit_up": bool(stock.get("is_limit_up")),
                    "candidate_flow_rank": stock.get("flow_rank"),
                    "candidate_liquidity_rank": stock.get("liquidity_rank"),
                    "candidate_binding_source": stock.get("binding_source"),
                    "candidate_leader_role": stock.get("leader_role"),
                    "candidate_leader_claim": stock.get("leader_claim"),
                    "candidate_leader_tier": stock.get("leader_tier"),
                    "candidate_strategic_score": stock.get("strategic_score"),
                    "candidate_seed_score": stock.get("seed_score"),
                    "candidate_evidence_score": stock.get("evidence_score"),
                    "candidate_evidence_count": stock.get("evidence_count"),
                    "candidate_hard_evidence_count": stock.get("hard_evidence_count"),
                    "candidate_latest_evidence_date": stock.get("latest_evidence_date"),
                    "candidate_evidence_sources": stock.get("evidence_sources") or [],
                    "candidate_market_heat_score": stock.get("market_heat_score"),
                    "candidate_score_model": stock.get("score_model"),
                    "candidate_raw_factor_score": stock.get("raw_factor_score"),
                    "candidate_regime": stock.get("regime"),
                    "candidate_regime_multiplier": stock.get("regime_multiplier"),
                    "candidate_regime_reason": stock.get("regime_reason") or [],
                    "candidate_lifecycle_state": stock.get("stock_lifecycle_state"),
                    "candidate_lifecycle_confidence": stock.get("lifecycle_confidence"),
                    "candidate_lifecycle_multiplier": stock.get("lifecycle_multiplier"),
                    "candidate_lifecycle_reason": stock.get("lifecycle_reason") or [],
                    "candidate_factor_breakdown": stock.get("factor_breakdown") or [],
                    "queue_reason": queue_reason,
                }
            )
            priority += 1
    return queue


def _q(pro: Any, api_name: str, **kwargs: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return getattr(pro, api_name)(**kwargs)
        except Exception as exc:  # pragma: no cover - external API
            last_error = exc
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Tushare API failed: {api_name}") from last_error


def _date_window(basis_date: str) -> tuple[str, str]:
    end = datetime.strptime(_compact_date(basis_date), "%Y%m%d")
    start = end - timedelta(days=150)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _df_first(df: Any) -> dict[str, Any]:
    if df is None or getattr(df, "empty", True):
        return {}
    return dict(df.iloc[0])


def _latest_sorted_row(df: Any, sort_col: str) -> dict[str, Any]:
    if df is None or getattr(df, "empty", True) or sort_col not in df.columns:
        return _df_first(df)
    return dict(df.sort_values(sort_col, ascending=False).iloc[0])


def _compute_returns(daily: Any) -> dict[str, Any]:
    if daily is None or getattr(daily, "empty", True):
        return {}
    frame = daily.copy()
    frame["trade_date"] = frame["trade_date"].astype(str)
    frame = frame.sort_values("trade_date")
    if frame.empty:
        return {}
    current = frame.iloc[-1]
    close = safe_float(current.get("close"))
    result = {
        "close": _round(close),
        "pct_chg": _round(current.get("pct_chg")),
        "amount": _round(current.get("amount")),
    }
    for label, offset in (("r5", 5), ("r20", 20), ("r60", 60)):
        if close is None or len(frame) <= offset:
            result[label] = None
            continue
        prev_close = safe_float(frame.iloc[-offset - 1].get("close"))
        result[label] = _round((close / prev_close - 1) * 100 if prev_close else None)
    return result


def fetch_stock_diagnostics(codes: list[str], basis_date: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    token = get_tushare_token()
    if not token:
        return {}, ["Tushare token unavailable; stock deep diagnostics skipped"]
    try:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api(token)
    except Exception as exc:  # pragma: no cover - runtime dependency
        return {}, [f"Tushare runtime unavailable: {type(exc).__name__}"]

    start_date, end_date = _date_window(basis_date)
    trade_date = _compact_date(basis_date)
    diagnostics: dict[str, dict[str, Any]] = {}
    global_gaps: list[str] = []
    try:
        stock_basic_all = _q(pro, "stock_basic", exchange="", list_status="L", fields="ts_code,name,industry,market,list_date")
    except Exception as exc:
        stock_basic_all = None
        global_gaps.append(f"stock_basic unavailable: {type(exc).__name__}")

    for code in codes:
        gaps: list[str] = []
        risk_flags: list[str] = []
        basic = {}
        if stock_basic_all is not None and not getattr(stock_basic_all, "empty", True):
            rows = stock_basic_all[stock_basic_all["ts_code"].astype(str) == code]
            basic = _df_first(rows)
        else:
            gaps.append("缺少stock_basic")

        try:
            daily = _q(pro, "daily", ts_code=code, start_date=start_date, end_date=end_date)
            market = _compute_returns(daily)
            if not market:
                gaps.append("缺少daily行情")
        except Exception as exc:
            market = {}
            gaps.append(f"daily unavailable: {type(exc).__name__}")

        try:
            daily_basic = _q(pro, "daily_basic", ts_code=code, start_date=trade_date, end_date=trade_date)
            valuation = _df_first(daily_basic)
            if not valuation:
                gaps.append("缺少daily_basic估值")
        except Exception as exc:
            valuation = {}
            gaps.append(f"daily_basic unavailable: {type(exc).__name__}")

        try:
            fina = _q(pro, "fina_indicator", ts_code=code, start_date=(datetime.now() - timedelta(days=1100)).strftime("%Y%m%d"), end_date=trade_date)
            financial = _latest_sorted_row(fina, "end_date")
            if not financial:
                gaps.append("缺少fina_indicator财务指标")
        except Exception as exc:
            financial = {}
            gaps.append(f"fina_indicator unavailable: {type(exc).__name__}")

        try:
            moneyflow = _q(pro, "moneyflow", ts_code=code, start_date=trade_date, end_date=trade_date)
            flow = _df_first(moneyflow)
            if flow:
                flow["large_net"] = (
                    (safe_float(flow.get("buy_lg_amount")) or 0.0)
                    + (safe_float(flow.get("buy_elg_amount")) or 0.0)
                    - (safe_float(flow.get("sell_lg_amount")) or 0.0)
                    - (safe_float(flow.get("sell_elg_amount")) or 0.0)
                )
            else:
                gaps.append("缺少moneyflow")
        except Exception as exc:
            flow = {}
            gaps.append(f"moneyflow unavailable: {type(exc).__name__}")

        try:
            namechange = _q(pro, "namechange", ts_code=code)
            names = " ".join(str(row.get("name", "")) for row in (namechange.to_dict("records") if namechange is not None and not namechange.empty else []))
            current_name = str(basic.get("name") or "")
            if "ST" in names or "ST" in current_name:
                risk_flags.append("ST/名称风险")
            if "退" in names or "退" in current_name:
                risk_flags.append("退市名称风险")
        except Exception:
            gaps.append("namechange风险检查缺失")

        diagnostics[code] = {
            "basic": basic,
            "market": market,
            "valuation": valuation,
            "financial": financial,
            "moneyflow": flow,
            "risk_flags": risk_flags,
            "data_gaps": gaps,
        }
    return diagnostics, global_gaps


def _theme_binding_score(item: dict[str, Any]) -> float:
    candidate = safe_float(item.get("candidate_leader_score")) or 0.0
    theme_score = safe_float(item.get("theme_score")) or 0.0
    seed = safe_float(item.get("candidate_seed_score"))
    if seed is None:
        seed = safe_float(item.get("candidate_strategic_score"))
    if seed is not None and math.isnan(float(seed)):
        seed = None
    evidence = safe_float(item.get("candidate_evidence_score")) or 35.0
    if math.isnan(float(evidence)):
        evidence = 35.0
    grade_bonus = {"S": 10.0, "A": 8.0, "B": 4.0, "C": 0.0, "D": -12.0}.get(str(item.get("candidate_grade") or ""), 0.0)
    tier_bonus = {
        "证据确认龙头": 10.0,
        "强候选龙头": 5.0,
        "市场热点候选": 0.0,
        "证据不足候选": -10.0,
    }.get(str(item.get("candidate_leader_tier") or ""), 0.0)
    seed_component = seed if seed is not None else candidate
    return _clamp(candidate * 0.35 + evidence * 0.25 + theme_score * 0.20 + seed_component * 0.12 + grade_bonus + tier_bonus)


def _financial_quality(financial: dict[str, Any], data_gaps: list[str]) -> float:
    if not financial:
        data_gaps.append("财务质量指标缺失")
        return 42.0
    roe = _rescale(financial.get("roe"), 0.0, 18.0)
    gross = _rescale(financial.get("grossprofit_margin"), 10.0, 45.0)
    net_margin = _rescale(financial.get("netprofit_margin"), 0.0, 20.0)
    revenue_yoy = _rescale(financial.get("or_yoy"), -10.0, 40.0)
    profit_yoy = _rescale(financial.get("netprofit_yoy"), -25.0, 65.0)
    debt = 100.0 - _rescale(financial.get("debt_to_assets"), 25.0, 85.0)
    ocf = _rescale(financial.get("ocf_to_or"), 0.0, 20.0)
    return _clamp(roe * 0.20 + gross * 0.14 + net_margin * 0.12 + revenue_yoy * 0.16 + profit_yoy * 0.18 + debt * 0.10 + ocf * 0.10)


def _valuation_safety(valuation: dict[str, Any], data_gaps: list[str]) -> float:
    if not valuation:
        data_gaps.append("估值指标缺失")
        return 45.0
    pe = safe_float(valuation.get("pe_ttm") or valuation.get("pe"))
    pb = safe_float(valuation.get("pb"))
    pe_score: float
    if pe is None:
        data_gaps.append("PE缺失")
        pe_score = 45.0
    elif pe <= 0:
        pe_score = 30.0
    elif pe <= 25:
        pe_score = 92.0
    elif pe <= 45:
        pe_score = 78.0
    elif pe <= 70:
        pe_score = 58.0
    elif pe <= 100:
        pe_score = 40.0
    else:
        pe_score = 24.0
    pb_score = 45.0 if pb is None else 100.0 - _rescale(pb, 1.0, 10.0)
    if pb is None:
        data_gaps.append("PB缺失")
    return _clamp(pe_score * 0.62 + pb_score * 0.38)


def _trading_structure(item: dict[str, Any], diagnostics: dict[str, Any]) -> tuple[float, list[str]]:
    market = diagnostics.get("market") or {}
    valuation = diagnostics.get("valuation") or {}
    flow = diagnostics.get("moneyflow") or {}
    flags: list[str] = []
    pct_chg = safe_float(market.get("pct_chg") if market.get("pct_chg") is not None else item.get("candidate_pct_chg"))
    r5 = safe_float(market.get("r5"))
    r20 = safe_float(market.get("r20"))
    turnover = safe_float(valuation.get("turnover_rate") if valuation.get("turnover_rate") is not None else item.get("candidate_turnover_rate"))
    liquidity = safe_float(item.get("candidate_liquidity_rank"))
    flow_rank = safe_float(item.get("candidate_flow_rank"))
    large_net = safe_float(flow.get("large_net"))
    score = _safe_mean(
        [
            _rescale(pct_chg, -4.0, 10.0),
            _rescale(r5, -6.0, 18.0) if r5 is not None else None,
            _rescale(r20, -12.0, 32.0) if r20 is not None else None,
            _rescale(turnover, 1.0, 18.0),
            _clamp((liquidity or 0.45) * 100.0),
            _clamp((flow_rank or 0.45) * 100.0 if large_net is None or large_net > 0 else 35.0),
        ]
    )
    if safe_float(r5) is not None and float(r5) >= 18.0:
        flags.append("5日涨幅偏热")
        score -= 10.0
    if safe_float(r20) is not None and float(r20) >= 35.0:
        flags.append("20日涨幅偏热")
        score -= 12.0
    if turnover is not None and turnover >= 25.0:
        flags.append("换手偏高")
        score -= 8.0
    if item.get("candidate_is_limit_up"):
        flags.append("涨停强化但需防次日分歧")
    return _clamp(score), flags


def _build_stock_item(queue_item: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
    code = str(queue_item.get("code") or "")
    diag = diagnostics.get(code) or {}
    data_gaps = list(diag.get("data_gaps") or [])
    risk_flags = list(diag.get("risk_flags") or [])
    theme_score = _theme_binding_score(queue_item)
    financial_score = _financial_quality(diag.get("financial") or {}, data_gaps)
    valuation_score = _valuation_safety(diag.get("valuation") or {}, data_gaps)
    trading_score, trading_flags = _trading_structure(queue_item, diag)
    risk_flags.extend(trading_flags)
    data_quality = _clamp(100.0 - len(set(data_gaps)) * 12.0, 40.0, 100.0)
    total = _clamp(theme_score * 0.30 + financial_score * 0.30 + valuation_score * 0.18 + trading_score * 0.17 + data_quality * 0.05)
    rating = _deep_rating(total, risk_flags=list(dict.fromkeys(risk_flags)), data_gaps=list(dict.fromkeys(data_gaps)))
    basic = diag.get("basic") or {}
    valuation = diag.get("valuation") or {}
    market = diag.get("market") or {}
    financial = diag.get("financial") or {}
    return {
        "priority": queue_item.get("priority"),
        "code": code,
        "name": queue_item.get("name") or basic.get("name") or code,
        "industry": queue_item.get("industry") or basic.get("industry") or "",
        "theme": queue_item.get("theme"),
        "theme_grade": queue_item.get("theme_grade"),
        "theme_score": queue_item.get("theme_score"),
        "theme_stage": queue_item.get("theme_stage"),
        "theme_lifecycle_state": queue_item.get("theme_lifecycle_state"),
        "candidate_grade": queue_item.get("candidate_grade"),
        "candidate_leader_score": queue_item.get("candidate_leader_score"),
        "candidate_binding_source": queue_item.get("candidate_binding_source"),
        "candidate_leader_role": queue_item.get("candidate_leader_role"),
        "candidate_leader_claim": queue_item.get("candidate_leader_claim") or queue_item.get("candidate_leader_role"),
        "candidate_leader_tier": queue_item.get("candidate_leader_tier"),
        "candidate_strategic_score": queue_item.get("candidate_strategic_score"),
        "candidate_seed_score": queue_item.get("candidate_seed_score"),
        "candidate_evidence_score": queue_item.get("candidate_evidence_score"),
        "candidate_evidence_count": queue_item.get("candidate_evidence_count"),
        "candidate_hard_evidence_count": queue_item.get("candidate_hard_evidence_count"),
        "candidate_latest_evidence_date": queue_item.get("candidate_latest_evidence_date"),
        "candidate_evidence_sources": queue_item.get("candidate_evidence_sources") or [],
        "candidate_market_heat_score": queue_item.get("candidate_market_heat_score"),
        "candidate_score_model": queue_item.get("candidate_score_model"),
        "candidate_raw_factor_score": queue_item.get("candidate_raw_factor_score"),
        "candidate_regime": queue_item.get("candidate_regime"),
        "candidate_regime_multiplier": queue_item.get("candidate_regime_multiplier"),
        "candidate_regime_reason": queue_item.get("candidate_regime_reason") or [],
        "candidate_lifecycle_state": queue_item.get("candidate_lifecycle_state"),
        "candidate_lifecycle_confidence": queue_item.get("candidate_lifecycle_confidence"),
        "candidate_lifecycle_multiplier": queue_item.get("candidate_lifecycle_multiplier"),
        "candidate_lifecycle_reason": queue_item.get("candidate_lifecycle_reason") or [],
        "candidate_factor_breakdown": queue_item.get("candidate_factor_breakdown") or [],
        "deep_score": round(total, 2),
        "deep_rating": rating,
        "deep_label": _rating_label(rating),
        "shadow_observation_eligible": rating in {"S", "A"},
        "scores": {
            "theme_binding": round(theme_score, 2),
            "evidence_quality": _round(queue_item.get("candidate_evidence_score")),
            "financial_quality": round(financial_score, 2),
            "valuation_safety": round(valuation_score, 2),
            "trading_structure": round(trading_score, 2),
            "data_quality": round(data_quality, 2),
        },
        "market": {
            "close": _round(market.get("close")),
            "pct_chg": _round(market.get("pct_chg") if market.get("pct_chg") is not None else queue_item.get("candidate_pct_chg")),
            "r5": _round(market.get("r5")),
            "r20": _round(market.get("r20")),
            "r60": _round(market.get("r60")),
            "turnover_rate": _round(valuation.get("turnover_rate") if valuation.get("turnover_rate") is not None else queue_item.get("candidate_turnover_rate")),
            "pe_ttm": _round(valuation.get("pe_ttm") or valuation.get("pe")),
            "pb": _round(valuation.get("pb")),
        },
        "financial": {
            "end_date": financial.get("end_date"),
            "roe": _round(financial.get("roe")),
            "grossprofit_margin": _round(financial.get("grossprofit_margin")),
            "netprofit_margin": _round(financial.get("netprofit_margin")),
            "or_yoy": _round(financial.get("or_yoy")),
            "netprofit_yoy": _round(financial.get("netprofit_yoy")),
            "debt_to_assets": _round(financial.get("debt_to_assets")),
            "ocf_to_or": _round(financial.get("ocf_to_or")),
        },
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "data_gaps": list(dict.fromkeys(data_gaps)),
        "research_boundary": "ResearchFirst; read_only; no_trade_order; no_cash_or_share_amounts",
        "queue_reason": queue_item.get("queue_reason"),
    }


def build_stock_shadow_contract(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "mode": "stock_research_input",
        "report_id": payload.get("report_id"),
        "leader_report_id": payload.get("leader_report_id"),
        "basis_date": payload.get("basis_date"),
        "generated_at": payload.get("generated_at"),
        "constraints": {
            "read_only": True,
            "ratio_only": True,
            "contains_trade_orders": False,
            "contains_cash_amounts": False,
            "contains_share_counts": False,
            "source": "MyInvestLeader.stock_deep",
        },
        "stock_signals": [
            {
                "priority": row.get("priority"),
                "code": row.get("code"),
                "name": row.get("name"),
                "theme": row.get("theme"),
                "deep_rating": row.get("deep_rating"),
                "deep_score": row.get("deep_score"),
                "leader_claim": row.get("candidate_leader_claim"),
                "leader_tier": row.get("candidate_leader_tier"),
                "evidence_score": row.get("candidate_evidence_score"),
                "evidence_count": row.get("candidate_evidence_count"),
                "hard_evidence_count": row.get("candidate_hard_evidence_count"),
                "score_model": row.get("candidate_score_model"),
                "raw_factor_score": row.get("candidate_raw_factor_score"),
                "regime": row.get("candidate_regime"),
                "regime_multiplier": row.get("candidate_regime_multiplier"),
                "regime_reason": row.get("candidate_regime_reason") or [],
                "lifecycle_state": row.get("candidate_lifecycle_state"),
                "lifecycle_confidence": row.get("candidate_lifecycle_confidence"),
                "lifecycle_multiplier": row.get("candidate_lifecycle_multiplier"),
                "lifecycle_reason": row.get("candidate_lifecycle_reason") or [],
                "factor_breakdown": row.get("candidate_factor_breakdown") or [],
                "shadow_observation_eligible": row.get("shadow_observation_eligible"),
                "risk_flags": row.get("risk_flags") or [],
                "data_gaps": row.get("data_gaps") or [],
            }
            for row in payload.get("stocks") or []
        ],
        "data_gaps": payload.get("data_gaps") or [],
    }


def build_stock_deep_report(
    leader_payload: dict[str, Any],
    *,
    max_per_theme: int = 3,
    diagnostics: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any], str]:
    report_id = _now_report_id()
    basis_date = str(leader_payload.get("basis_date") or datetime.now(TZ).date().isoformat())
    queue = select_deep_queue(leader_payload, max_per_theme=max_per_theme)
    codes = [str(item.get("code")) for item in queue if item.get("code")]
    global_gaps: list[str] = []
    diagnostics_map = diagnostics
    if diagnostics_map is None:
        diagnostics_map, global_gaps = fetch_stock_diagnostics(codes, basis_date)
    stocks = [_build_stock_item(item, diagnostics_map or {}) for item in queue]
    rating_counts = {rating: 0 for rating in ("S", "A", "B", "C")}
    for row in stocks:
        rating = row.get("deep_rating")
        if rating in rating_counts:
            rating_counts[rating] += 1
    all_gaps = sorted(set([*global_gaps, *(gap for row in stocks for gap in (row.get("data_gaps") or []))]))
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "leader_report_id": leader_payload.get("report_id"),
        "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CST"),
        "basis_date": basis_date,
        "constraints": {
            "read_only": True,
            "research_first": True,
            "ratio_only_for_shadow": True,
            "contains_trade_orders": False,
            "contains_cash_amounts": False,
            "contains_share_counts": False,
        },
        "queue": queue,
        "stocks": sorted(stocks, key=lambda row: (row.get("priority") or 999, -float(row.get("deep_score") or 0.0))),
        "summary": {
            "queue_count": len(queue),
            "stock_count": len(stocks),
            "eligible_count": sum(1 for row in stocks if row.get("shadow_observation_eligible")),
            "evidence_confirmed_count": sum(1 for row in stocks if row.get("candidate_leader_tier") == "证据确认龙头"),
            "rating_counts": rating_counts,
            "top_stock": stocks[0].get("name") if stocks else "",
            "data_gap_count": len(all_gaps),
        },
        "data_gaps": all_gaps,
    }
    payload["shadow_contract"] = build_stock_shadow_contract(payload)
    return report_id, payload, render_markdown(payload)


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# A股龙头股深度研究：{payload.get('basis_date')}",
        "",
        f"- 报告ID：{payload.get('report_id')}",
        f"- 上游龙头报告：{payload.get('leader_report_id')}",
        f"- 生成时间：{payload.get('generated_at')}",
        "- 边界：ResearchFirst，只读研究；不含交易指令、资金金额、股数或真实持仓。",
        "",
        "## 深研队列",
        "",
        "| 优先级 | 股票 | 主线 | 龙头认定 | 龙头角色 | 证据分 | 证据数 | 候选分 | 深研分 | 评级 | 影子池 |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in payload.get("stocks") or []:
        eligible = "入选" if row.get("shadow_observation_eligible") else "未入选"
        lines.append(
            f"| {row.get('priority')} | {row.get('code')} {row.get('name')} | {row.get('theme')} | {row.get('candidate_leader_tier') or ''} | {row.get('candidate_leader_claim') or ''} | {row.get('candidate_evidence_score') or ''} | {row.get('candidate_evidence_count') or 0}/{row.get('candidate_hard_evidence_count') or 0} | {row.get('candidate_leader_score')} | {row.get('deep_score'):.2f} | {row.get('deep_rating')} {row.get('deep_label')} | {eligible} |"
        )
    for row in payload.get("stocks") or []:
        scores = row.get("scores") or {}
        market = row.get("market") or {}
        financial = row.get("financial") or {}
        evidence_items = row.get("candidate_evidence_sources") or []
        evidence_text = "；".join(
            f"{source.get('type')}[{source.get('source_name')}]: {source.get('summary')}"
            for source in evidence_items[:5]
        )
        lines += [
            "",
            f"## {row.get('code')} {row.get('name')}：{row.get('deep_label')}",
            "",
            f"- 主线：{row.get('theme')}；主线分层：{row.get('theme_grade')}；候选分：{row.get('candidate_leader_score')}",
            f"- 龙头认定：{row.get('candidate_leader_tier') or '未分层'}；角色：{row.get('candidate_leader_claim') or '未标注'}；证据分：{row.get('candidate_evidence_score')}；证据数：{row.get('candidate_evidence_count') or 0}；硬证据：{row.get('candidate_hard_evidence_count') or 0}",
            f"- 证据链：{evidence_text or '暂无证据项'}",
            f"- 深研分：{row.get('deep_score'):.2f}；评级：{row.get('deep_rating')}；影子池：{'入选' if row.get('shadow_observation_eligible') else '未入选'}",
            f"- 评分拆解：主题绑定 {scores.get('theme_binding')}；证据质量 {scores.get('evidence_quality')}；财务质量 {scores.get('financial_quality')}；估值安全 {scores.get('valuation_safety')}；交易结构 {scores.get('trading_structure')}；数据质量 {scores.get('data_quality')}",
            f"- 交易结构：1日 {market.get('pct_chg')}%；5日 {market.get('r5')}%；20日 {market.get('r20')}%；换手 {market.get('turnover_rate')}%；PE(TTM) {market.get('pe_ttm')}；PB {market.get('pb')}",
            f"- 财务指标：期末 {financial.get('end_date') or '缺失'}；ROE {financial.get('roe')}；毛利率 {financial.get('grossprofit_margin')}；收入同比 {financial.get('or_yoy')}；归母净利同比 {financial.get('netprofit_yoy')}；资产负债率 {financial.get('debt_to_assets')}",
            f"- 风险标记：{'、'.join(row.get('risk_flags') or []) or '无'}",
            f"- 数据缺口：{'、'.join(row.get('data_gaps') or []) or '无'}",
        ]
    lines += ["", "## 全局数据缺口", ""]
    gaps = payload.get("data_gaps") or []
    lines.extend(f"- {gap}" for gap in gaps) if gaps else lines.append("- 无")
    return "\n".join(lines)


def write_stock_deep_report(
    report_id: str,
    payload: dict[str, Any],
    markdown: str,
    report_dir: Path = STOCK_REPORT_DIR,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{report_id}.json"
    md_path = report_dir / f"{report_id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path
