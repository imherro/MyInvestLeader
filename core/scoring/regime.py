from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class MarketRegime(str, Enum):
    BULL_STRONG = "BULL_STRONG"
    BULL_WEAK = "BULL_WEAK"
    SIDEWAYS = "SIDEWAYS"
    BEAR = "BEAR"


REGIME_MULTIPLIERS = {
    MarketRegime.BULL_STRONG: 1.10,
    MarketRegime.BULL_WEAK: 1.00,
    MarketRegime.SIDEWAYS: 0.85,
    MarketRegime.BEAR: 0.70,
}


@dataclass(frozen=True)
class RegimeResult:
    regime: str
    multiplier: float
    reason: list[str]
    features: dict[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _index_values(indexes: list[dict[str, Any]], key: str) -> list[float]:
    result = []
    for item in indexes:
        value = _num(item.get(key))
        if value is not None:
            result.append(value)
    return result


def detect_market_regime(market_context: dict[str, Any] | None) -> RegimeResult:
    context = market_context or {}
    breadth = context.get("breadth") or {}
    indexes = context.get("broad_indexes") or []
    r5_values = _index_values(indexes, "r5")
    r20_values = _index_values(indexes, "r20")
    r1_values = _index_values(indexes, "r1")

    index_momentum_5d = _avg(r5_values)
    index_momentum_20d = _avg(r20_values)
    advance_decline_ratio = (_num(breadth.get("up_ratio")) or 50.0) / 100.0
    volume_expansion_ratio = (
        _num(context.get("volume_expansion_ratio"))
        or _num(breadth.get("volume_expansion_ratio"))
        or 1.0
    )
    volatility_proxy = None
    if len(r1_values) >= 2:
        volatility_proxy = statistics.pstdev(r1_values)
    elif len(r5_values) >= 2:
        volatility_proxy = statistics.pstdev(r5_values)

    reasons: list[str] = []
    if index_momentum_5d is None or index_momentum_20d is None:
        reasons.append("index momentum unavailable; neutral fallback")
        regime = MarketRegime.BULL_WEAK
    else:
        if index_momentum_5d >= 5.0 and index_momentum_20d >= 2.0:
            reasons.append("index momentum strong positive")
            momentum_state = "strong_positive"
        elif index_momentum_5d > 0.0 and index_momentum_20d >= 0.0:
            reasons.append("index momentum positive")
            momentum_state = "positive"
        elif index_momentum_5d <= -3.0 or index_momentum_20d <= -5.0:
            reasons.append("index momentum negative")
            momentum_state = "negative"
        else:
            reasons.append("index momentum mixed")
            momentum_state = "mixed"

        if advance_decline_ratio >= 0.55:
            reasons.append("breadth positive")
            breadth_state = "positive"
        elif advance_decline_ratio < 0.42:
            reasons.append("breadth weak")
            breadth_state = "weak"
        else:
            reasons.append("breadth neutral")
            breadth_state = "neutral"

        if volume_expansion_ratio >= 1.10:
            reasons.append("volume expanding")
        elif volume_expansion_ratio <= 0.90:
            reasons.append("volume contracting")
        else:
            reasons.append("volume neutral or unavailable")

        if volatility_proxy is not None and volatility_proxy >= 2.8:
            reasons.append("volatility elevated")
            volatility_state = "elevated"
        else:
            reasons.append("volatility moderate")
            volatility_state = "moderate"

        if momentum_state == "strong_positive" and breadth_state == "positive" and volatility_state == "moderate":
            regime = MarketRegime.BULL_STRONG
        elif momentum_state in {"strong_positive", "positive"} and breadth_state != "weak":
            regime = MarketRegime.BULL_WEAK
        elif momentum_state == "negative" and breadth_state == "weak":
            regime = MarketRegime.BEAR
        else:
            regime = MarketRegime.SIDEWAYS

    return RegimeResult(
        regime=regime.value,
        multiplier=REGIME_MULTIPLIERS[regime],
        reason=reasons,
        features={
            "index_momentum_5d": round(index_momentum_5d, 6) if index_momentum_5d is not None else None,
            "index_momentum_20d": round(index_momentum_20d, 6) if index_momentum_20d is not None else None,
            "advance_decline_ratio": round(advance_decline_ratio, 6),
            "volume_expansion_ratio": round(volume_expansion_ratio, 6),
            "volatility_proxy": round(volatility_proxy, 6) if volatility_proxy is not None else None,
        },
    )
