from __future__ import annotations

from core.scoring import calculate_score, detect_market_regime


def context_for(r5: float, r20: float, up_ratio: float, r1_values: list[float] | None = None) -> dict:
    values = r1_values or [0.6, 0.8, 0.7]
    return {
        "breadth": {"up_ratio": up_ratio},
        "broad_indexes": [
            {"code": "000300.SH", "r1": values[0], "r5": r5, "r20": r20},
            {"code": "000905.SH", "r1": values[1], "r5": r5 + 0.4, "r20": r20 + 0.2},
            {"code": "399006.SZ", "r1": values[2], "r5": r5 - 0.2, "r20": r20 - 0.1},
        ],
    }


def sample_stock() -> dict:
    return {
        "seed_score": 96.0,
        "keyword_match": True,
        "evidence_score": 82.0,
        "leader_tier": "证据确认龙头",
        "pct_chg": 2.0,
        "turnover_rate": 5.0,
        "amount": 500000.0,
        "amount_rank": 0.85,
        "flow_rank": 0.80,
        "large_net": 200.0,
        "is_limit_up": False,
        "mv_rank": 0.90,
        "total_mv": 900000.0,
        "industry": "半导体",
    }


def test_detects_three_market_regimes() -> None:
    assert detect_market_regime(context_for(6.0, 3.0, 62.0)).regime == "BULL_STRONG"
    assert detect_market_regime(context_for(0.2, -0.5, 50.0)).regime == "SIDEWAYS"
    assert detect_market_regime(context_for(-4.0, -6.0, 35.0)).regime == "BEAR"


def test_regime_changes_same_stock_score() -> None:
    stock = sample_stock()
    universe = [
        {**stock, "amount": 400000.0, "large_net": 150.0, "total_mv": 800000.0},
        stock,
        {**stock, "amount": 600000.0, "large_net": 250.0, "total_mv": 1000000.0},
    ]

    bull_score = calculate_score(stock, universe, context_for(6.0, 3.0, 62.0))
    bear_score = calculate_score(stock, universe, context_for(-4.0, -6.0, 35.0))

    assert bull_score > bear_score
    assert bull_score / bear_score > 1.4
