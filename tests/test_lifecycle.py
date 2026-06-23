from __future__ import annotations

from core.scoring import FactorResult, calculate_score, detect_leader_lifecycle


def factor(name: str, value: float, weight: float = 0.25) -> FactorResult:
    return FactorResult(name=name, value=value, weight=weight, score=value * weight, evidence={})


def factors(theme: float, volume: float, flow: float, cap: float = 0.5) -> list[FactorResult]:
    return [
        factor("theme_strength", theme),
        factor("volume_activity", volume),
        factor("fund_flow", flow),
        factor("cap_quality", cap),
    ]


def test_detects_leader_lifecycle_states() -> None:
    expansion = detect_leader_lifecycle(
        {"pct_chg": 1.0, "turnover_rate": 8.0, "leader_tier": "证据确认龙头"},
        factors(0.90, 0.80, 0.75),
        "BULL_WEAK",
    )
    breakout = detect_leader_lifecycle(
        {"pct_chg": 5.0, "turnover_rate": 10.0, "leader_tier": "证据确认龙头"},
        factors(0.70, 0.85, 0.55),
        "BULL_WEAK",
    )
    decline = detect_leader_lifecycle(
        {"pct_chg": -4.5, "turnover_rate": 2.0, "leader_tier": "证据不足候选"},
        factors(0.20, 0.30, 0.20),
        "BEAR",
    )

    assert expansion.state == "Expansion"
    assert expansion.stage_score_multiplier == 1.2
    assert breakout.state == "Breakout"
    assert breakout.stage_score_multiplier == 1.1
    assert decline.state == "Decline"
    assert decline.stage_score_multiplier == 0.6


def test_lifecycle_changes_same_stock_score() -> None:
    base = {
        "seed_score": 90.0,
        "keyword_match": True,
        "evidence_score": 80.0,
        "leader_tier": "证据确认龙头",
        "pct_chg": 1.0,
        "turnover_rate": 6.0,
        "amount": 500000.0,
        "amount_rank": 0.8,
        "flow_rank": 0.8,
        "large_net": 100.0,
        "is_limit_up": False,
        "mv_rank": 0.8,
        "total_mv": 500000.0,
        "industry": "半导体",
    }
    expansion_stock = base
    decline_stock = {
        **base,
        "pct_chg": -5.0,
        "turnover_rate": 2.0,
        "amount": 10000.0,
        "large_net": -100.0,
        "leader_tier": "证据不足候选",
    }
    universe = [
        expansion_stock,
        {**base, "amount": 300000.0, "large_net": 80.0, "total_mv": 300000.0},
        {**base, "amount": 700000.0, "large_net": 150.0, "total_mv": 700000.0},
    ]
    market = {
        "breadth": {"up_ratio": 55.0},
        "broad_indexes": [{"r1": 0.5, "r5": 2.0, "r20": 1.0}, {"r1": 0.6, "r5": 2.5, "r20": 1.2}],
    }

    expansion_score = calculate_score(expansion_stock, universe, market)
    decline_score = calculate_score(decline_stock, [decline_stock, *universe[1:]], market)

    assert expansion_score > decline_score
