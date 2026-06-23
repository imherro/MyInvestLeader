from __future__ import annotations

from typing import Any

from .factors import BaseFactor, CapQualityFactor, FundFlowFactor, ThemeFactor, VolumeFactor
from .lifecycle import detect_leader_lifecycle
from .regime import detect_market_regime


class ScoringEngine:
    def __init__(self, factors: list[BaseFactor]):
        self.factors = factors

    def score(
        self,
        stock_context: dict[str, Any],
        stock_universe: list[dict[str, Any]] | None = None,
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        universe = stock_universe or [stock_context]
        results = []
        raw_factor_score = 0.0
        for factor in self.factors:
            peer_contexts = factor.comparison_contexts(stock_context, universe)
            universe_values = [factor.compute_raw(item) for item in peer_contexts]
            result = factor.compute(stock_context, universe_values)
            results.append(result)
            raw_factor_score += result.score
        regime = detect_market_regime(market_context)
        lifecycle = detect_leader_lifecycle(stock_context, results, regime.regime)
        total = raw_factor_score * regime.multiplier * lifecycle.stage_score_multiplier
        return {
            "score": max(0.0, min(1.0, total)),
            "raw_factor_score": max(0.0, min(1.0, raw_factor_score)),
            "factors": results,
            "regime": regime,
            "lifecycle": lifecycle,
        }

    def score_many(
        self,
        stock_universe: list[dict[str, Any]],
        market_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return [self.score(stock, stock_universe, market_context) for stock in stock_universe]


def default_stock_scoring_engine() -> ScoringEngine:
    return ScoringEngine(
        factors=[
            ThemeFactor(),
            VolumeFactor(),
            FundFlowFactor(),
            CapQualityFactor(),
        ]
    )


def calculate_score(
    stock: dict[str, Any],
    stock_universe: list[dict[str, Any]] | None = None,
    market_context: dict[str, Any] | None = None,
) -> float:
    result = default_stock_scoring_engine().score(stock, stock_universe, market_context)
    return max(0.0, min(100.0, float(result["score"]) * 100.0))


def calculate_score_breakdown(
    stock: dict[str, Any],
    stock_universe: list[dict[str, Any]] | None = None,
    market_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = default_stock_scoring_engine().score(stock, stock_universe, market_context)
    factors = [factor.to_dict() for factor in result["factors"]]
    regime = result["regime"].to_dict()
    lifecycle = result["lifecycle"].to_dict()
    return {
        "model": "factorized_scoring_engine.v1",
        "score": round(float(result["score"]) * 100.0, 6),
        "raw_factor_score": round(float(result["raw_factor_score"]) * 100.0, 6),
        "normalized_score": round(float(result["score"]), 6),
        "regime": regime,
        "lifecycle": lifecycle,
        "factors": factors,
        "weights": {factor["name"]: factor["weight"] for factor in factors},
    }
