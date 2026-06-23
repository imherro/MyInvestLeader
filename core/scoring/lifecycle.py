from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .schema import FactorResult


LIFECYCLE_MULTIPLIERS = {
    "Accumulation": 0.90,
    "Breakout": 1.10,
    "Expansion": 1.20,
    "Distribution": 0.85,
    "Decline": 0.60,
}


@dataclass(frozen=True)
class LifecycleResult:
    state: str
    confidence: float
    reason: list[str]
    stage_score_multiplier: float
    features: dict[str, float | bool | str | None]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _factor_value(factors: list[FactorResult], name: str) -> float:
    for factor in factors:
        if factor.name == name:
            return float(factor.value)
    return 0.5


def _confidence(matches: int, total: int) -> float:
    if total <= 0:
        return 0.5
    return round(max(0.35, min(0.95, matches / total)), 4)


def detect_leader_lifecycle(
    stock_context: dict[str, Any],
    factors: list[FactorResult],
    regime: str | None = None,
) -> LifecycleResult:
    theme = _factor_value(factors, "theme_strength")
    volume = _factor_value(factors, "volume_activity")
    flow = _factor_value(factors, "fund_flow")
    pct_chg = _num(stock_context.get("pct_chg")) or 0.0
    turnover = _num(stock_context.get("turnover_rate")) or 0.0
    is_limit_up = bool(stock_context.get("is_limit_up"))
    market_heat = _num(stock_context.get("market_heat_score")) or 50.0
    leader_tier = str(stock_context.get("leader_tier") or "")
    regime_label = regime or "BULL_WEAK"

    features: dict[str, float | bool | str | None] = {
        "theme_value": round(theme, 6),
        "volume_value": round(volume, 6),
        "flow_value": round(flow, 6),
        "pct_chg": pct_chg,
        "turnover_rate": turnover,
        "is_limit_up": is_limit_up,
        "market_heat_score": market_heat,
        "leader_tier": leader_tier,
        "regime": regime_label,
    }

    decline_matches = [
        theme < 0.35,
        volume < 0.35,
        flow < 0.30,
        pct_chg <= -3.0,
        regime_label == "BEAR",
    ]
    if sum(decline_matches) >= 3:
        return LifecycleResult(
            state="Decline",
            confidence=_confidence(sum(decline_matches), len(decline_matches)),
            reason=[
                "theme leadership weak",
                "volume or flow confirmation lost",
                "price momentum/regime pressure negative",
            ],
            stage_score_multiplier=LIFECYCLE_MULTIPLIERS["Decline"],
            features=features,
        )

    distribution_matches = [
        volume >= 0.75,
        flow <= 0.40,
        turnover >= 18.0 or market_heat >= 82.0,
        pct_chg <= 1.0,
    ]
    if sum(distribution_matches) >= 3:
        return LifecycleResult(
            state="Distribution",
            confidence=_confidence(sum(distribution_matches), len(distribution_matches)),
            reason=[
                "activity remains high",
                "fund flow diverges from activity",
                "momentum no longer confirms leadership",
            ],
            stage_score_multiplier=LIFECYCLE_MULTIPLIERS["Distribution"],
            features=features,
        )

    expansion_matches = [
        theme >= 0.80,
        volume >= 0.70,
        flow >= 0.60,
        pct_chg >= 0.0,
        regime_label != "BEAR",
    ]
    if sum(expansion_matches) >= 4:
        return LifecycleResult(
            state="Expansion",
            confidence=_confidence(sum(expansion_matches), len(expansion_matches)),
            reason=[
                "theme leadership confirmed",
                "relative volume and fund flow remain strong",
                "market regime does not block trend extension",
            ],
            stage_score_multiplier=LIFECYCLE_MULTIPLIERS["Expansion"],
            features=features,
        )

    breakout_matches = [
        theme >= 0.60,
        volume >= 0.75,
        flow >= 0.50,
        pct_chg >= 3.0 or is_limit_up,
    ]
    if sum(breakout_matches) >= 3:
        return LifecycleResult(
            state="Breakout",
            confidence=_confidence(sum(breakout_matches), len(breakout_matches)),
            reason=[
                "volume spike confirms first leadership appearance",
                "theme and flow support early breakout",
            ],
            stage_score_multiplier=LIFECYCLE_MULTIPLIERS["Breakout"],
            features=features,
        )

    accumulation_matches = [
        theme >= 0.45,
        volume < 0.65,
        flow >= 0.45,
        leader_tier in {"证据确认龙头", "强候选龙头"},
    ]
    return LifecycleResult(
        state="Accumulation",
        confidence=_confidence(sum(accumulation_matches), len(accumulation_matches)),
        reason=[
            "leadership evidence exists but activity has not fully expanded",
            "candidate remains in research-first accumulation state",
        ],
        stage_score_multiplier=LIFECYCLE_MULTIPLIERS["Accumulation"],
        features=features,
    )
