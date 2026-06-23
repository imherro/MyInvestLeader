from __future__ import annotations

from typing import Any

from core.scoring import BaseFactor, FactorResult, ScoringEngine, calculate_score, calculate_score_breakdown, percentile_rank


def legacy_score(context: dict[str, Any]) -> float:
    pct_score = max(0.0, min(100.0, (context["pct_chg"] - -4.0) / (10.0 - -4.0) * 100.0))
    turnover_score = max(0.0, min(100.0, (context["turnover_rate"] - 1.0) / (16.0 - 1.0) * 100.0))
    liquidity_score = max(0.0, min(100.0, context["amount_rank"] * 100.0))
    flow_score = 35.0 if context["large_net"] <= 0 else max(0.0, min(100.0, context["flow_rank"] * 100.0))
    limit_score = 100.0 if context["is_limit_up"] else 45.0
    mv_score = max(0.0, min(100.0, context["mv_rank"] * 100.0))
    market_heat = (
        pct_score * 0.22
        + turnover_score * 0.16
        + liquidity_score * 0.20
        + flow_score * 0.22
        + limit_score * 0.14
        + mv_score * 0.06
    )
    seed_score = context["seed_score"]
    binding_score = 82.0
    evidence_score = context["evidence_score"]
    return max(0.0, min(100.0, seed_score * 0.35 + binding_score * 0.20 + market_heat * 0.25 + evidence_score * 0.20))


def sample_context() -> dict[str, Any]:
    return {
        "seed_score": 98.0,
        "keyword_match": True,
        "evidence_score": 87.79,
        "leader_tier": "证据确认龙头",
        "pct_chg": 0.5,
        "turnover_rate": 2.0,
        "amount_rank": 0.75,
        "flow_rank": 0.70,
        "large_net": 100.0,
        "is_limit_up": False,
        "mv_rank": 0.98,
    }


def test_factorized_score_matches_legacy_formula() -> None:
    context = sample_context()
    new_score = calculate_score(context)
    old_score = legacy_score(context)

    assert abs(new_score - old_score) <= old_score * 0.01


def test_breakdown_has_required_factor_names() -> None:
    breakdown = calculate_score_breakdown(sample_context())
    factors = breakdown["factors"]

    assert breakdown["model"] == "factorized_scoring_engine.v1"
    assert {row["name"] for row in factors} == {"theme_strength", "volume_activity", "fund_flow", "cap_quality"}
    assert round(sum(row["weight"] for row in factors), 6) == 1.0
    assert all(0.0 <= row["value"] <= 1.0 for row in factors)


def test_percentile_rank_uses_midpoint_ties() -> None:
    assert percentile_rank([10.0, 20.0, 30.0], 20.0) == 0.5
    assert percentile_rank([20.0, 20.0, 20.0], 20.0) == 0.5


def test_same_raw_value_changes_across_universes() -> None:
    stock = {**sample_context(), "amount": 100.0, "total_mv": 100.0, "large_net": 100.0}
    weak_universe = [
        {**stock, "amount": 10.0, "total_mv": 10.0, "large_net": 10.0},
        stock,
        {**stock, "amount": 20.0, "total_mv": 20.0, "large_net": 20.0},
    ]
    strong_universe = [
        {**stock, "amount": 1000.0, "total_mv": 1000.0, "large_net": 1000.0},
        stock,
        {**stock, "amount": 2000.0, "total_mv": 2000.0, "large_net": 2000.0},
    ]

    weak_score = calculate_score(stock, weak_universe)
    strong_score = calculate_score(stock, strong_universe)

    assert weak_score > strong_score


def test_engine_accepts_plugin_factor_without_changes() -> None:
    class ConstantFactor(BaseFactor):
        name = "constant"
        weight = 0.5

        def compute_raw(self, context: dict[str, Any]) -> float:
            return 80.0

    result = ScoringEngine([ConstantFactor()]).score({})

    assert result["score"] == 0.4
    assert result["factors"][0].name == "constant"
