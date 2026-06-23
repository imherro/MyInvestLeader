from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


LIFECYCLE_SIGNAL = {
    "Accumulation": 0.68,
    "Breakout": 0.88,
    "Expansion": 1.00,
    "Distribution": 0.42,
    "Decline": 0.18,
}


@dataclass(frozen=True)
class CorrelationGuard:
    correlation: float
    threshold: float
    dominance_weight: float
    factor_weight: float
    action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConvergenceResult:
    ulls: float
    raw_ulls: float
    tier: str | None
    explanations: dict[str, Any]
    correlation_guard: CorrelationGuard
    smoothed: bool
    previous_ulls: float | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["correlation_guard"] = self.correlation_guard.to_dict()
        return payload


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pearson_correlation(left: list[float], right: list[float]) -> float:
    pairs = [(float(a), float(b)) for a, b in zip(left, right) if math.isfinite(float(a)) and math.isfinite(float(b))]
    if len(pairs) < 3:
        return 0.0
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    mean_x = _mean(xs)
    mean_y = _mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x <= 0 or denom_y <= 0:
        return 0.0
    return _clamp(numerator / (denom_x * denom_y), -1.0, 1.0)


def build_correlation_guard(factor_scores: list[float], dominance_scores: list[float], threshold: float = 0.78) -> CorrelationGuard:
    correlation = pearson_correlation(factor_scores, dominance_scores)
    abs_correlation = abs(correlation)
    if abs_correlation >= threshold:
        dominance_weight = 0.04
        action = "downgrade_competition_to_explanation"
    elif abs_correlation >= threshold * 0.82:
        dominance_weight = 0.08
        action = "partial_competition_downgrade"
    else:
        dominance_weight = 0.12
        action = "keep_competition_normalizer"
    factor_weight = 0.74 - dominance_weight
    return CorrelationGuard(
        correlation=round(correlation, 6),
        threshold=threshold,
        dominance_weight=dominance_weight,
        factor_weight=factor_weight,
        action=action,
    )


def calculate_ulls(
    *,
    factor_score: float,
    lifecycle_state: str,
    regime_multiplier: float,
    dominance: float,
    guard: CorrelationGuard,
    previous_ulls: float | None = None,
    tier: str | None = None,
) -> ConvergenceResult:
    factor_signal = _clamp(factor_score)
    lifecycle_signal = LIFECYCLE_SIGNAL.get(lifecycle_state, 0.58)
    regime_signal = _clamp(regime_multiplier / 1.10)
    dominance_signal = _clamp(dominance)
    weights = {
        "factor_score": guard.factor_weight,
        "lifecycle": 0.16,
        "regime": 0.10,
        "dominance_normalizer": guard.dominance_weight,
    }
    raw_ulls = _clamp(
        factor_signal * weights["factor_score"]
        + lifecycle_signal * weights["lifecycle"]
        + regime_signal * weights["regime"]
        + dominance_signal * weights["dominance_normalizer"]
    )
    smoothed = previous_ulls is not None
    ulls = _clamp(raw_ulls * 0.70 + _clamp(previous_ulls or 0.0) * 0.30) if smoothed else raw_ulls
    explanations = {
        "factor_score": round(factor_signal, 6),
        "lifecycle": {
            "state": lifecycle_state,
            "signal": round(lifecycle_signal, 6),
        },
        "regime": {
            "multiplier": round(regime_multiplier, 6),
            "signal": round(regime_signal, 6),
        },
        "dominance": {
            "signal": round(dominance_signal, 6),
            "role": "explanatory_normalizer",
        },
        "weights": {key: round(value, 6) for key, value in weights.items()},
    }
    return ConvergenceResult(
        ulls=round(ulls, 6),
        raw_ulls=round(raw_ulls, 6),
        tier=tier,
        explanations=explanations,
        correlation_guard=guard,
        smoothed=smoothed,
        previous_ulls=round(previous_ulls, 6) if previous_ulls is not None else None,
    )
