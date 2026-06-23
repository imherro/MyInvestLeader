from __future__ import annotations

from typing import Any

from .factors import BaseFactor, CapQualityFactor, FundFlowFactor, ThemeFactor, VolumeFactor


class ScoringEngine:
    def __init__(self, factors: list[BaseFactor]):
        self.factors = factors

    def score(self, stock_context: dict[str, Any]) -> dict[str, Any]:
        results = []
        total = 0.0
        for factor in self.factors:
            result = factor.compute(stock_context)
            results.append(result)
            total += result.score
        return {
            "score": max(0.0, min(1.0, total)),
            "factors": results,
        }


def default_stock_scoring_engine() -> ScoringEngine:
    return ScoringEngine(
        factors=[
            ThemeFactor(),
            VolumeFactor(),
            FundFlowFactor(),
            CapQualityFactor(),
        ]
    )


def calculate_score(stock: dict[str, Any]) -> float:
    result = default_stock_scoring_engine().score(stock)
    return max(0.0, min(100.0, float(result["score"]) * 100.0))


def calculate_score_breakdown(stock: dict[str, Any]) -> dict[str, Any]:
    result = default_stock_scoring_engine().score(stock)
    factors = [factor.to_dict() for factor in result["factors"]]
    return {
        "model": "factorized_scoring_engine.v1",
        "score": round(float(result["score"]) * 100.0, 6),
        "normalized_score": round(float(result["score"]), 6),
        "factors": factors,
        "weights": {factor["name"]: factor["weight"] for factor in factors},
    }
