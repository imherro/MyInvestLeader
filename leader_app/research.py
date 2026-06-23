from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from core.scoring import calculate_score, calculate_score_breakdown

from .config import DEFAULT_THEME_API_URL, REPORT_DIR, ROOT_DIR, get_tushare_token
from .pricing import PricePoint, fetch_tushare_fund_prices, safe_float
from .upstream import fetch_json, latest_result, parse_etf_candidates, stable_hash


TZ = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "leader_research.v1"
SHADOW_SCHEMA_VERSION = "leader_shadow_input.v1"

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "硬科技电子/半导体": ("半导体", "芯片", "电子", "元件", "PCB", "集成电路", "消费电子", "光学"),
    "AI算力/通信": ("通信", "算力", "光模块", "CPO", "5G", "人工智能", "AI", "服务器", "软件", "互联网"),
    "高端制造/机器人/军工": ("机器人", "自动化", "机床", "军工", "装备", "机械", "航空", "航天", "船舶"),
    "建材/稳增长修复": ("建材", "水泥", "玻璃", "基建", "建筑", "装修", "非金属"),
    "新能源/电力设备": ("电池", "锂电", "光伏", "风电", "储能", "新能源", "电力设备", "电网"),
    "资源周期": ("有色", "小金属", "铜", "铝", "黄金", "稀土", "煤炭", "石油", "钢铁"),
    "消费/传媒": ("消费", "传媒", "游戏", "影视", "旅游", "家电", "食品", "饮料", "零售"),
    "创新药/医药": ("医药", "创新药", "医疗", "器械", "生物", "制药", "中药", "CRO"),
}

LIFECYCLE_SCORE = {
    "accelerating": 96.0,
    "sustained": 88.0,
    "emerging": 78.0,
    "single_event_emerging": 68.0,
    "cooling": 48.0,
    "legacy_tail": 40.0,
    "dormant": 22.0,
    "unknown": 45.0,
}

LEADER_UNIVERSE_PATH = ROOT_DIR / "config" / "stock_leader_universe.json"
LEADER_EVIDENCE_PATH = ROOT_DIR / "config" / "leader_evidence_sources.json"


def _compact_date(value: str | None) -> str:
    return (value or "").replace("-", "")


def _now_report_id() -> str:
    return f"leader_review_{datetime.now(TZ).strftime('%Y-%m-%d_%H%M%S')}"


def _round(value: Any, digits: int = 4) -> float | None:
    number = safe_float(value)
    if number is None or math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _rescale(value: Any, low: float, high: float) -> float:
    number = safe_float(value)
    if number is None:
        return 45.0
    if high <= low:
        return 45.0
    return _clamp((number - low) / (high - low) * 100.0)


def _grade(score: float) -> str:
    if score >= 82:
        return "A"
    if score >= 68:
        return "B"
    if score >= 54:
        return "C"
    return "D"


def _leader_label(grade: str) -> str:
    return {
        "A": "核心龙头",
        "B": "弹性龙头",
        "C": "观察标的",
        "D": "不落地",
    }.get(grade, "观察标的")


def _stage_weight(stage: str | None) -> float:
    label = stage or ""
    if "主线确认" in label:
        return 1.0
    if "次主线" in label or "强修复" in label:
        return 0.92
    if "观察" in label:
        return 0.74
    if "弱势" in label or "退潮" in label:
        return 0.35
    return 0.6


def _theme_score(row: dict[str, Any]) -> float:
    evidence = safe_float(row.get("evidence_score")) or 0.0
    market = safe_float(row.get("market_score")) or 0.0
    etf = safe_float(row.get("etf_score")) or 0.0
    policy = safe_float(row.get("policy_score")) or 0.0
    lifecycle = LIFECYCLE_SCORE.get(str(row.get("lifecycle_state") or "unknown"), 45.0)
    score = evidence * 0.42 + market * 0.24 + etf * 0.16 + policy * 0.10 + lifecycle * 0.08
    return _clamp(score * _stage_weight(row.get("stage")))


def _theme_keywords(row: dict[str, Any]) -> tuple[str, ...]:
    base = list(THEME_KEYWORDS.get(str(row.get("theme") or ""), ()))
    for field in ("top_sw", "top_ths"):
        text = str(row.get(field) or "")
        for item in text.replace("、", ",").replace("，", ",").split(","):
            item = item.strip()
            if 2 <= len(item) <= 8:
                base.append(item)
    seen: set[str] = set()
    result = []
    for item in base:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _keyword_match(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _load_stock_leader_universe() -> dict[str, Any]:
    if not LEADER_UNIVERSE_PATH.exists():
        return {"themes": {}}
    try:
        return json.loads(LEADER_UNIVERSE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"themes": {}}


def _load_leader_evidence_sources() -> dict[str, Any]:
    if not LEADER_EVIDENCE_PATH.exists():
        return {"source_rules": [], "manual_records": []}
    try:
        return json.loads(LEADER_EVIDENCE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"source_rules": [], "manual_records": []}


def _strategic_seed_map(theme_name: str) -> dict[str, dict[str, Any]]:
    store = _load_stock_leader_universe()
    themes = store.get("themes") or {}
    return {
        str(item.get("code")): item
        for item in (themes.get(theme_name) or [])
        if item.get("code")
    }


def _manual_evidence_map(theme_name: str) -> dict[str, dict[str, Any]]:
    store = _load_leader_evidence_sources()
    records = store.get("manual_records") or []
    return {
        str(item.get("code")): item
        for item in records
        if item.get("code") and str(item.get("theme") or "") == theme_name
    }


def _evidence_rule(rule_type: str) -> dict[str, Any]:
    store = _load_leader_evidence_sources()
    for rule in store.get("source_rules") or []:
        if str(rule.get("type") or "") == rule_type:
            return dict(rule)
    return {
        "type": rule_type,
        "source_name": "local_computed",
        "source_kind": "computed_dynamic",
        "confidence": 0.5,
        "hard_evidence": False,
    }


def _evidence_item(rule_type: str, summary: str, as_of_date: str, confidence: float | None = None) -> dict[str, Any]:
    rule = _evidence_rule(rule_type)
    item_confidence = safe_float(confidence if confidence is not None else rule.get("confidence"))
    return {
        "type": rule_type,
        "summary": summary,
        "source_name": rule.get("source_name") or "local_computed",
        "source_kind": rule.get("source_kind") or "computed_dynamic",
        "as_of_date": as_of_date,
        "confidence": round(float(item_confidence if item_confidence is not None else 0.5), 4),
        "hard_evidence": bool(rule.get("hard_evidence")),
    }


def _leader_evidence_score(items: list[dict[str, Any]]) -> float:
    if not items:
        return 25.0
    weighted = 0.0
    total_weight = 0.0
    evidence_types: set[str] = set()
    hard_count = 0
    for item in items:
        confidence = safe_float(item.get("confidence")) or 0.0
        hard = bool(item.get("hard_evidence"))
        weight = 1.18 if hard else 0.76
        weighted += _clamp(confidence * 100.0) * weight
        total_weight += weight
        if item.get("type"):
            evidence_types.add(str(item.get("type")))
        if hard:
            hard_count += 1
    base = weighted / total_weight if total_weight else 25.0
    diversity_bonus = min(12.0, max(0, len(evidence_types) - 1) * 3.0)
    hard_bonus = min(10.0, hard_count * 3.5)
    return _clamp(base + diversity_bonus + hard_bonus)


def _leader_tier(
    *,
    has_seed_claim: bool,
    keyword_match: bool,
    evidence_score: float,
    hard_evidence_count: int,
    market_heat_score: float,
) -> str:
    if has_seed_claim and hard_evidence_count >= 2 and evidence_score >= 70.0:
        return "证据确认龙头"
    if has_seed_claim:
        return "强候选龙头"
    if keyword_match and hard_evidence_count >= 2 and market_heat_score >= 68.0:
        return "市场热点候选"
    return "证据不足候选"


def _binding_source_for_tier(tier: str) -> str:
    return {
        "证据确认龙头": "候选种子+动态证据确认",
        "强候选龙头": "候选种子+待补证据",
        "市场热点候选": "关键词/行业匹配+市场确认",
        "证据不足候选": "证据不足",
    }.get(tier, "证据不足")


def _build_leader_evidence_profile(
    *,
    row: Any,
    theme_row: dict[str, Any],
    seed_map: dict[str, dict[str, Any]],
    manual_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    code = str(row.get("ts_code") or "")
    seed = seed_map.get(code) or {}
    manual = manual_map.get(code) or {}
    basis_date = str(theme_row.get("basis_date") or "")
    as_of_date = basis_date or datetime.now(TZ).date().isoformat()
    keyword_hit = bool(row.get("keyword_match"))
    evidence: list[dict[str, Any]] = []
    leader_claim = str(manual.get("leader_claim") or seed.get("role") or "")

    if seed:
        claim = leader_claim or "候选种子"
        seed_score = safe_float(seed.get("strategic_score"))
        confidence = 0.5 + min(0.12, max(0.0, ((seed_score or 80.0) - 80.0) / 200.0))
        evidence.append(
            _evidence_item(
                "industry_role_seed",
                f"候选种子库标注：{claim}",
                as_of_date,
                confidence=confidence,
            )
        )

    if keyword_hit:
        text_hit = str(row.get("industry") or row.get("name") or "")
        evidence.append(
            _evidence_item(
                "mainline_binding",
                f"当前主线关键词命中：{text_hit or '名称/行业'}",
                as_of_date,
            )
        )

    mv_rank = safe_float(row.get("mv_rank"))
    if mv_rank is not None and mv_rank >= 0.90:
        evidence.append(
            _evidence_item(
                "market_scale",
                f"总市值处于全A股前 {round((1.0 - mv_rank) * 100.0, 1)}% 区间",
                as_of_date,
                confidence=0.72 + min(0.1, (mv_rank - 0.90) * 0.7),
            )
        )

    amount_rank = safe_float(row.get("amount_rank"))
    if amount_rank is not None and amount_rank >= 0.80:
        evidence.append(
            _evidence_item(
                "liquidity_confirmation",
                f"成交额分位 {round(amount_rank * 100.0, 1)}%",
                as_of_date,
                confidence=0.62 + min(0.1, (amount_rank - 0.80) * 0.5),
            )
        )

    flow_rank = safe_float(row.get("flow_rank"))
    large_net = safe_float(row.get("large_net"))
    if large_net is not None and large_net > 0 and flow_rank is not None and flow_rank >= 0.70:
        evidence.append(
            _evidence_item(
                "capital_flow",
                f"大单净流入为正，资金流分位 {round(flow_rank * 100.0, 1)}%",
                as_of_date,
                confidence=0.56 + min(0.1, (flow_rank - 0.70) * 0.5),
            )
        )

    score = _leader_evidence_score(evidence)
    hard_count = sum(1 for item in evidence if item.get("hard_evidence"))
    market_heat = safe_float(row.get("market_heat_score")) or _market_heat_score(row)
    tier = _leader_tier(
        has_seed_claim=bool(seed or manual),
        keyword_match=keyword_hit,
        evidence_score=score,
        hard_evidence_count=hard_count,
        market_heat_score=market_heat,
    )
    latest_date = max((str(item.get("as_of_date") or "") for item in evidence), default="")
    return {
        "leader_claim": leader_claim or ("关键词强势候选" if keyword_hit else ""),
        "leader_tier": tier,
        "binding_source": _binding_source_for_tier(tier),
        "evidence_score": round(score, 2),
        "evidence_count": len(evidence),
        "hard_evidence_count": hard_count,
        "latest_evidence_date": latest_date,
        "evidence_sources": evidence,
    }


def _clean_point(point: PricePoint | None) -> dict[str, Any]:
    if not point:
        return {"source": "missing"}
    return {
        "source": point.source,
        "has_close": point.close is not None,
        "pct_chg": _round(point.pct_chg, 4),
        "r5": _round(point.r5, 4),
        "r20": _round(point.r20, 4),
        "amount_rank": _round(point.amount_rank, 4),
        "premium_rate": _round(point.premium_rate, 4),
        "error": point.error,
    }


def _etf_score(row: dict[str, Any], point: PricePoint | None) -> float:
    source_score = safe_float(row.get("score"))
    if source_score is None and point:
        source_score = safe_float(point.amount_rank)
        if source_score is not None and source_score <= 1.0:
            source_score *= 100.0
    if source_score is None:
        source_score = 55.0
    r5 = safe_float(row.get("r5")) if row else None
    r20 = safe_float(row.get("r20")) if row else None
    if r5 is None and point:
        r5 = point.r5
    if r20 is None and point:
        r20 = point.r20
    trend = _rescale(r5, -6.0, 18.0) * 0.45 + _rescale(r20, -12.0, 30.0) * 0.55
    amount_rank = safe_float(row.get("amount_rank")) if row else None
    if amount_rank is None and point:
        amount_rank = point.amount_rank
    liquidity = (amount_rank * 100.0) if amount_rank is not None and amount_rank <= 1.0 else (amount_rank or 55.0)
    score = source_score * 0.55 + trend * 0.25 + _clamp(liquidity) * 0.20
    return _clamp(score)


def _risk_flags(r5: Any, r20: Any, premium_rate: Any = None) -> list[str]:
    flags: list[str] = []
    r5_value = safe_float(r5)
    r20_value = safe_float(r20)
    premium = safe_float(premium_rate)
    if r5_value is not None and r5_value >= 18.0:
        flags.append("5日涨幅偏热")
    if r20_value is not None and r20_value >= 30.0:
        flags.append("20日涨幅偏热")
    if premium is not None and abs(premium) >= 2.0:
        flags.append("净值溢价/折价偏离")
    return flags


def _build_etf_leaders(
    theme_row: dict[str, Any],
    etf_top: list[dict[str, Any]],
    price_map: dict[str, PricePoint],
) -> list[dict[str, Any]]:
    keywords = _theme_keywords(theme_row)
    parsed = parse_etf_candidates(str(theme_row.get("top_etf") or ""))
    by_code = {str(row.get("ts_code") or row.get("code") or ""): row for row in etf_top}
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parsed:
        candidates.append(item)
        seen.add(item["code"])
    for row in etf_top:
        code = str(row.get("ts_code") or row.get("code") or "")
        name = str(row.get("name") or "")
        if code and code not in seen and _keyword_match(name, keywords):
            candidates.append({"code": code, "name": name or code})
            seen.add(code)
        if len(candidates) >= 8:
            break

    leaders: list[dict[str, Any]] = []
    for item in candidates[:8]:
        row = by_code.get(item["code"], {})
        point = price_map.get(item["code"])
        score = _etf_score(row, point)
        grade = _grade(score)
        r5 = row.get("r5") if row else (point.r5 if point else None)
        r20 = row.get("r20") if row else (point.r20 if point else None)
        premium = point.premium_rate if point else None
        leaders.append(
            {
                "code": item["code"],
                "name": row.get("name") or item["name"],
                "leader_score": round(score, 2),
                "grade": grade,
                "role": _leader_label(grade),
                "pct_chg": _round(row.get("r1") if row else (point.pct_chg if point else None), 4),
                "r5": _round(r5, 4),
                "r20": _round(r20, 4),
                "source_score": _round(row.get("score"), 4) if row else None,
                "amount_rank": _round(row.get("amount_rank"), 4) if row else _round(point.amount_rank if point else None, 4),
                "price_source": _clean_point(point),
                "risk_flags": _risk_flags(r5, r20, premium),
                "data_gaps": [] if row or point else ["缺少ETF排名和行情补充"],
            }
        )
    return sorted(leaders, key=lambda row: (-float(row["leader_score"]), row["code"]))[:5]


def _q(pro: Any, api_name: str, **kwargs: Any) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return getattr(pro, api_name)(**kwargs)
        except Exception as exc:  # pragma: no cover - external API
            last_error = exc
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Tushare API failed: {api_name}") from last_error


def _stock_universe(basis_date: str) -> tuple[Any | None, list[str]]:
    data_gaps: list[str] = []
    token = get_tushare_token()
    if not token:
        return None, ["Tushare token unavailable; stock leaders skipped"]
    try:
        import pandas as pd
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api(token)
    except Exception as exc:  # pragma: no cover - runtime dependency
        return None, [f"Tushare runtime unavailable: {type(exc).__name__}"]

    trade_date = _compact_date(basis_date)
    try:
        daily = _q(pro, "daily", trade_date=trade_date, fields="ts_code,trade_date,close,pct_chg,amount")
        basic = _q(pro, "daily_basic", trade_date=trade_date, fields="ts_code,trade_date,total_mv,turnover_rate,pe_ttm,pb")
        stocks = _q(pro, "stock_basic", exchange="", list_status="L", fields="ts_code,name,industry,market")
    except Exception as exc:
        return None, [f"Tushare stock base tables unavailable: {type(exc).__name__}: {exc}"]

    if daily is None or daily.empty or basic is None or basic.empty:
        return None, ["Tushare daily/daily_basic incomplete; stock leaders skipped"]

    frame = daily.merge(basic, on=["ts_code", "trade_date"], how="left").merge(stocks, on="ts_code", how="left")
    try:
        moneyflow = _q(pro, "moneyflow", trade_date=trade_date)
        if moneyflow is not None and not moneyflow.empty:
            cols = set(moneyflow.columns)
            if {"buy_lg_amount", "buy_elg_amount", "sell_lg_amount", "sell_elg_amount"}.issubset(cols):
                moneyflow = moneyflow.copy()
                moneyflow["large_net"] = (
                    moneyflow["buy_lg_amount"].astype(float)
                    + moneyflow["buy_elg_amount"].astype(float)
                    - moneyflow["sell_lg_amount"].astype(float)
                    - moneyflow["sell_elg_amount"].astype(float)
                )
                frame = frame.merge(moneyflow[["ts_code", "net_mf_amount", "large_net"]], on="ts_code", how="left")
            else:
                data_gaps.append("moneyflow lacks large-order columns")
        else:
            data_gaps.append("moneyflow empty")
    except Exception as exc:
        data_gaps.append(f"moneyflow unavailable: {type(exc).__name__}")

    try:
        limit_df = _q(pro, "limit_list_d", trade_date=trade_date)
        limit_codes = set()
        if limit_df is not None and not limit_df.empty:
            if "limit" in limit_df.columns:
                limit_codes = set(limit_df.loc[limit_df["limit"].astype(str) == "U", "ts_code"].astype(str))
            elif "limit_type" in limit_df.columns:
                limit_codes = set(limit_df.loc[limit_df["limit_type"].astype(str).str.contains("涨", na=False), "ts_code"].astype(str))
        frame["is_limit_up"] = frame["ts_code"].astype(str).isin(limit_codes)
    except Exception as exc:
        data_gaps.append(f"limit_list_d unavailable: {type(exc).__name__}")
        frame["is_limit_up"] = False

    for column in ("amount", "turnover_rate", "large_net", "total_mv", "pct_chg"):
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["amount_rank"] = frame["amount"].rank(pct=True)
    frame["flow_rank"] = frame["large_net"].clip(lower=0).rank(pct=True)
    frame["mv_rank"] = frame["total_mv"].rank(pct=True)
    return frame, data_gaps


def _market_heat_score(row: Any) -> float:
    pct_score = _rescale(row.get("pct_chg"), -4.0, 10.0)
    turnover_score = _rescale(row.get("turnover_rate"), 1.0, 16.0)
    liquidity_score = _clamp(float(row.get("amount_rank") or 0.0) * 100.0)
    flow_rank = float(row.get("flow_rank") or 0.0)
    flow_score = 35.0 if float(row.get("large_net") or 0.0) <= 0 else _clamp(flow_rank * 100.0)
    limit_score = 100.0 if bool(row.get("is_limit_up")) else 45.0
    mv_score = _clamp(float(row.get("mv_rank") or 0.0) * 100.0)
    return _clamp(
        pct_score * 0.22
        + turnover_score * 0.16
        + liquidity_score * 0.20
        + flow_score * 0.22
        + limit_score * 0.14
        + mv_score * 0.06
    )


def _stock_score(row: Any, universe: list[dict[str, Any]] | None = None) -> float:
    return _clamp(calculate_score(row, universe))


def _stock_score_breakdown(row: Any, universe: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return calculate_score_breakdown(row, universe)


def _build_stock_leaders(theme_row: dict[str, Any], universe: Any | None) -> list[dict[str, Any]]:
    if universe is None:
        return []
    keywords = _theme_keywords(theme_row)
    if not keywords:
        return []
    seed_map = _strategic_seed_map(str(theme_row.get("theme") or ""))
    manual_map = _manual_evidence_map(str(theme_row.get("theme") or ""))
    text = (
        universe["name"].fillna("").astype(str)
        + " "
        + universe["industry"].fillna("").astype(str)
        + " "
        + universe["market"].fillna("").astype(str)
    )
    keyword_mask = text.apply(lambda value: _keyword_match(value, keywords))
    seed_mask = universe["ts_code"].astype(str).isin(set(seed_map))
    mask = keyword_mask | seed_mask
    matched = universe.loc[mask].copy()
    if matched.empty:
        return []
    matched["keyword_match"] = keyword_mask.loc[matched.index]
    matched["seed_score"] = matched["ts_code"].astype(str).map(
        lambda code: safe_float(seed_map.get(code, {}).get("strategic_score"))
    )
    matched["strategic_score"] = matched["seed_score"]
    matched["leader_role"] = matched["ts_code"].astype(str).map(
        lambda code: seed_map.get(code, {}).get("role") or ("关键词强势候选" if code not in seed_map else "")
    )
    matched["market_heat_score"] = matched.apply(_market_heat_score, axis=1)
    profiles = matched.apply(
        lambda row: _build_leader_evidence_profile(
            row=row,
            theme_row=theme_row,
            seed_map=seed_map,
            manual_map=manual_map,
        ),
        axis=1,
    )
    matched["leader_claim"] = profiles.apply(lambda item: item.get("leader_claim"))
    matched["leader_tier"] = profiles.apply(lambda item: item.get("leader_tier"))
    matched["binding_source"] = profiles.apply(lambda item: item.get("binding_source"))
    matched["evidence_score"] = profiles.apply(lambda item: item.get("evidence_score"))
    matched["evidence_count"] = profiles.apply(lambda item: item.get("evidence_count"))
    matched["hard_evidence_count"] = profiles.apply(lambda item: item.get("hard_evidence_count"))
    matched["latest_evidence_date"] = profiles.apply(lambda item: item.get("latest_evidence_date"))
    matched["evidence_sources"] = profiles.apply(lambda item: item.get("evidence_sources"))
    universe_records = matched.to_dict("records")
    matched["score_breakdown"] = matched.apply(lambda row: _stock_score_breakdown(row, universe_records), axis=1)
    matched["leader_score"] = matched["score_breakdown"].apply(lambda item: safe_float((item or {}).get("score")) or 0.0)
    matched = matched.sort_values(["leader_score", "evidence_score", "seed_score", "amount"], ascending=[False, False, False, False]).head(8)
    leaders = []
    for _, row in matched.iterrows():
        score = float(row.get("leader_score") or 0.0)
        grade = _grade(score)
        evidence_sources = row.get("evidence_sources") or []
        score_breakdown = row.get("score_breakdown") or {}
        leaders.append(
            {
                "code": str(row.get("ts_code") or ""),
                "name": str(row.get("name") or ""),
                "industry": str(row.get("industry") or ""),
                "leader_score": round(score, 2),
                "grade": grade,
                "role": _leader_label(grade),
                "leader_role": str(row.get("leader_role") or ""),
                "leader_claim": str(row.get("leader_claim") or row.get("leader_role") or ""),
                "leader_tier": str(row.get("leader_tier") or ""),
                "binding_source": str(row.get("binding_source") or ""),
                "seed_score": _round(row.get("seed_score"), 4),
                "strategic_score": _round(row.get("strategic_score"), 4),
                "evidence_score": _round(row.get("evidence_score"), 4),
                "evidence_count": int(safe_float(row.get("evidence_count")) or 0),
                "hard_evidence_count": int(safe_float(row.get("hard_evidence_count")) or 0),
                "latest_evidence_date": str(row.get("latest_evidence_date") or ""),
                "evidence_sources": evidence_sources,
                "market_heat_score": _round(row.get("market_heat_score"), 4),
                "pct_chg": _round(row.get("pct_chg"), 4),
                "turnover_rate": _round(row.get("turnover_rate"), 4),
                "is_limit_up": bool(row.get("is_limit_up")),
                "flow_rank": _round(row.get("flow_rank"), 4),
                "liquidity_rank": _round(row.get("amount_rank"), 4),
                "score_model": score_breakdown.get("model"),
                "factor_breakdown": score_breakdown.get("factors") or [],
                "data_gaps": [],
                "research_boundary": "research_only_no_trade_order",
            }
        )
    return leaders


def _candidate_fund_codes(theme_rows: list[dict[str, Any]], etf_top: list[dict[str, Any]]) -> list[str]:
    codes: set[str] = set()
    for row in theme_rows:
        for item in parse_etf_candidates(str(row.get("top_etf") or "")):
            codes.add(item["code"])
    for row in etf_top[:50]:
        code = str(row.get("ts_code") or row.get("code") or "")
        if code:
            codes.add(code)
    return sorted(codes)


def build_shadow_contract(payload: dict[str, Any]) -> dict[str, Any]:
    signals = []
    for theme in payload.get("themes") or []:
        score = safe_float(theme.get("leader_score")) or 0.0
        signals.append(
            {
                "rank": theme.get("rank"),
                "theme": theme.get("theme"),
                "theme_id": theme.get("theme_id"),
                "stage": theme.get("stage"),
                "lifecycle_state": theme.get("lifecycle_state"),
                "leader_score": score,
                "leader_grade": theme.get("leader_grade"),
                "score_weight_ratio": 0.0 if theme.get("leader_grade") == "D" else score,
                "top_etf": theme.get("top_etf_raw") or "",
                "etf_candidates": [
                    {
                        "code": row.get("code"),
                        "name": row.get("name"),
                        "leader_score": row.get("leader_score"),
                        "grade": row.get("grade"),
                        "pct_chg_ratio": row.get("pct_chg"),
                        "r5_ratio": row.get("r5"),
                        "r20_ratio": row.get("r20"),
                        "risk_flags": row.get("risk_flags") or [],
                    }
                    for row in (theme.get("etf_leaders") or [])[:5]
                ],
                "stock_candidates": [
                    {
                        "code": row.get("code"),
                        "name": row.get("name"),
                        "industry": row.get("industry"),
                        "leader_score": row.get("leader_score"),
                        "grade": row.get("grade"),
                        "leader_claim": row.get("leader_claim"),
                        "leader_tier": row.get("leader_tier"),
                        "evidence_score": row.get("evidence_score"),
                        "evidence_count": row.get("evidence_count"),
                        "hard_evidence_count": row.get("hard_evidence_count"),
                        "latest_evidence_date": row.get("latest_evidence_date"),
                        "binding_source": row.get("binding_source"),
                        "score_model": row.get("score_model"),
                        "factor_breakdown": row.get("factor_breakdown") or [],
                        "pct_chg_ratio": row.get("pct_chg"),
                        "research_only": True,
                    }
                    for row in (theme.get("stock_leaders") or [])[:5]
                ],
                "data_gaps": theme.get("data_gaps") or [],
            }
        )
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "mode": "simulation_input",
        "report_id": payload.get("report_id"),
        "theme_report_id": payload.get("upstream", {}).get("theme_report_id"),
        "basis_date": payload.get("basis_date"),
        "generated_at": payload.get("generated_at"),
        "constraints": {
            "read_only": True,
            "ratio_only": True,
            "contains_trade_orders": False,
            "contains_cash_amounts": False,
            "contains_share_counts": False,
            "source": "MyInvestLeader",
        },
        "leader_signals": signals,
        "data_gaps": payload.get("data_gaps") or [],
    }


def build_report(theme_payload: dict[str, Any] | None = None, theme_url: str = DEFAULT_THEME_API_URL) -> tuple[str, dict[str, Any], str]:
    raw_theme = theme_payload if theme_payload is not None else fetch_json(theme_url)
    result = latest_result(raw_theme)
    theme_rows = [dict(row) for row in (result.get("theme_ranking") or [])]
    etf_top = [dict(row) for row in (result.get("etf_top") or [])]
    basis_date = str(result.get("basis_date") or datetime.now(TZ).date().isoformat())
    report_id = _now_report_id()
    data_sources = (ROOT_DIR / "数据源.md").read_text(encoding="utf-8") if (ROOT_DIR / "数据源.md").exists() else ""
    fund_codes = _candidate_fund_codes(theme_rows, etf_top)
    price_map = fetch_tushare_fund_prices(fund_codes, basis_date)
    stock_universe, stock_gaps = _stock_universe(basis_date)

    themes: list[dict[str, Any]] = []
    all_data_gaps = list(stock_gaps)
    for index, row in enumerate(theme_rows, start=1):
        score = _theme_score(row)
        grade = _grade(score)
        etf_leaders = _build_etf_leaders(row, etf_top, price_map)
        stock_leaders = _build_stock_leaders({**row, "basis_date": basis_date}, stock_universe)
        theme_gaps = []
        if not etf_leaders:
            theme_gaps.append("未形成ETF龙头候选")
        if stock_universe is None:
            theme_gaps.append("A股候选因Tushare缺口未生成")
        elif not stock_leaders:
            theme_gaps.append("未匹配到A股龙头候选")
        all_data_gaps.extend(theme_gaps)
        themes.append(
            {
                "rank": index,
                "theme_id": row.get("theme_id") or "",
                "theme": row.get("theme") or "",
                "stage": row.get("stage") or "",
                "lifecycle_state": row.get("lifecycle_state") or "",
                "leader_score": round(score, 2),
                "leader_grade": grade,
                "leader_label": _leader_label(grade),
                "evidence_score": _round(row.get("evidence_score"), 4),
                "market_score": _round(row.get("market_score"), 4),
                "policy_score": _round(row.get("policy_score"), 4),
                "mainline_score_v6": _round(row.get("mainline_score_v6"), 4),
                "sw_score": _round(row.get("sw_score"), 4),
                "ths_score": _round(row.get("ths_score"), 4),
                "etf_score": _round(row.get("etf_score"), 4),
                "limit_count": int(safe_float(row.get("limit_count")) or 0),
                "large_net": _round(row.get("large_net"), 4),
                "top_sw": row.get("top_sw") or "",
                "top_ths": row.get("top_ths") or "",
                "top_etf_raw": row.get("top_etf") or "",
                "top_policy": row.get("top_policy") or "",
                "lifecycle_reasons": row.get("lifecycle_reasons") or [],
                "keywords": list(_theme_keywords(row)),
                "etf_leaders": etf_leaders,
                "stock_leaders": stock_leaders,
                "data_gaps": theme_gaps,
            }
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CST"),
        "basis_date": basis_date,
        "nominal_today": result.get("nominal_today"),
        "data_sources_root": data_sources,
        "constraints": {
            "read_only": True,
            "ratio_only_for_shadow": True,
            "contains_trade_orders": False,
            "contains_real_position": False,
        },
        "upstream": {
            "theme_url": theme_url,
            "theme_report_id": raw_theme.get("report_id"),
            "theme_generated_at": result.get("generated_at"),
            "theme_content_hash": stable_hash(raw_theme),
            "basis_completeness": result.get("completeness") or {},
        },
        "market_context": {
            "breadth": result.get("breadth") or {},
            "broad_indexes": result.get("broad_indexes") or [],
        },
        "leader_summary": {
            "theme_count": len(themes),
            "etf_candidate_count": sum(len(row.get("etf_leaders") or []) for row in themes),
            "stock_candidate_count": sum(len(row.get("stock_leaders") or []) for row in themes),
            "evidence_confirmed_stock_count": sum(
                1
                for theme in themes
                for row in (theme.get("stock_leaders") or [])
                if row.get("leader_tier") == "证据确认龙头"
            ),
            "top_theme": themes[0].get("theme") if themes else "",
            "top_grade": themes[0].get("leader_grade") if themes else "",
            "data_gap_count": len(set(all_data_gaps)),
        },
        "themes": themes,
        "source_links": result.get("source_links") or {},
        "data_gaps": sorted(set(all_data_gaps)),
    }
    payload["shadow_contract"] = build_shadow_contract(payload)
    return report_id, payload, render_markdown(payload)


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# A股主线龙头研究：{payload.get('basis_date')}",
        "",
        f"- 报告ID：{payload.get('report_id')}",
        f"- 生成时间：{payload.get('generated_at')}",
        f"- 主线来源：{payload.get('upstream', {}).get('theme_report_id')}",
        f"- 约束：只读研究；不含真实持仓、资金金额、股数或交易指令。",
        "",
        "## 主线龙头总览",
        "",
        "| 排名 | 主线 | 阶段 | 龙头分 | 分层 | ETF候选 | A股候选 |",
        "| --- | --- | --- | ---: | --- | ---: | ---: |",
    ]
    for item in payload.get("themes") or []:
        lines.append(
            f"| {item.get('rank')} | {item.get('theme')} | {item.get('stage')} | {item.get('leader_score'):.2f} | {item.get('leader_label')} | {len(item.get('etf_leaders') or [])} | {len(item.get('stock_leaders') or [])} |"
        )
    for item in payload.get("themes") or []:
        lines += [
            "",
            f"## {item.get('rank')}. {item.get('theme')}：{item.get('leader_label')}",
            "",
            f"- 阶段：{item.get('stage')}；生命周期：{item.get('lifecycle_state')}",
            f"- 龙头分：{item.get('leader_score'):.2f}；等级：{item.get('leader_grade')}",
            f"- 证据分：{item.get('evidence_score')}；市场分：{item.get('market_score')}；政策分：{item.get('policy_score')}；mainline_score_v6：{item.get('mainline_score_v6')}",
            f"- 申万映射：{item.get('top_sw') or '无'}",
            f"- 同花顺映射：{item.get('top_ths') or '无'}",
            f"- 主要政策：{item.get('top_policy') or '无'}",
            "",
            "### ETF龙头候选",
            "",
            "| 代码 | 名称 | 分数 | 等级 | 1日 | 5日 | 20日 | 风险标记 |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
        ]
        for etf in item.get("etf_leaders") or []:
            lines.append(
                f"| {etf.get('code')} | {etf.get('name')} | {etf.get('leader_score'):.2f} | {etf.get('grade')} | {etf.get('pct_chg') or ''} | {etf.get('r5') or ''} | {etf.get('r20') or ''} | {'、'.join(etf.get('risk_flags') or []) or '无'} |"
            )
        if not item.get("etf_leaders"):
            lines.append("| - | - | - | - | - | - | - | 未形成ETF候选 |")
        lines += [
            "",
            "### A股龙头候选",
            "",
            "| 代码 | 名称 | 行业 | 龙头认定 | 龙头角色 | 分数 | 证据分 | 证据数 | 硬证据 | 来源 | 1日 | 换手 |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
        for stock in item.get("stock_leaders") or []:
            lines.append(
                f"| {stock.get('code')} | {stock.get('name')} | {stock.get('industry')} | {stock.get('leader_tier') or ''} | {stock.get('leader_claim') or stock.get('leader_role') or ''} | {stock.get('leader_score'):.2f} | {stock.get('evidence_score') or ''} | {stock.get('evidence_count') or 0} | {stock.get('hard_evidence_count') or 0} | {stock.get('binding_source') or ''} | {stock.get('pct_chg') or ''} | {stock.get('turnover_rate') or ''} |"
            )
        if not item.get("stock_leaders"):
            lines.append("| - | - | - | - | - | - | - | - | - | - | - | 数据不足或未匹配 |")
        else:
            lines += ["", "证据链摘要："]
            for stock in item.get("stock_leaders") or []:
                evidence_items = stock.get("evidence_sources") or []
                summaries = [
                    f"{source.get('type')}[{source.get('source_name')}]: {source.get('summary')}"
                    for source in evidence_items[:4]
                ]
                lines.append(
                    f"- {stock.get('code')} {stock.get('name')}：{stock.get('leader_tier')}；{'; '.join(summaries) or '暂无证据项'}"
                )
        if item.get("data_gaps"):
            lines += ["", "数据缺口："]
            lines.extend(f"- {gap}" for gap in item.get("data_gaps") or [])
    lines += [
        "",
        "## 数据缺口",
        "",
    ]
    gaps = payload.get("data_gaps") or []
    lines.extend(f"- {gap}" for gap in gaps) if gaps else lines.append("- 无")
    lines += [
        "",
        "## 数据源",
        "",
        payload.get("data_sources_root") or "未提供",
        "",
    ]
    return "\n".join(lines)


def write_report(report_id: str, payload: dict[str, Any], markdown: str, report_dir: Path = REPORT_DIR) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{report_id}.json"
    md_path = report_dir / f"{report_id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path
