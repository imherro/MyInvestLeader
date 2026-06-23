from __future__ import annotations

import math
from typing import Any

from .schema import FactorResult


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _rescale(value: Any, low: float, high: float) -> float:
    number = _safe_float(value)
    if number is None or high <= low:
        return 0.45
    return _clamp((number - low) / (high - low), 0.0, 1.0)


def _percent_rank(value: Any) -> float:
    return _clamp(_safe_float(value) or 0.0, 0.0, 1.0)


def _seed_score(context: dict[str, Any]) -> float:
    seed = _safe_float(context.get("seed_score"))
    if seed is None:
        seed = 56.0 if bool(context.get("keyword_match")) else 40.0
    return _clamp(seed / 100.0, 0.0, 1.0)


def _binding_score(context: dict[str, Any]) -> float:
    raw_seed = _safe_float(context.get("seed_score"))
    has_seed = raw_seed is not None
    keyword_match = bool(context.get("keyword_match"))
    if keyword_match and has_seed:
        return 0.82
    if has_seed:
        return 0.76
    if keyword_match:
        return 0.70
    return 0.45


def _evidence_score(context: dict[str, Any]) -> float:
    return _clamp((_safe_float(context.get("evidence_score")) or 35.0) / 100.0, 0.0, 1.0)


def _flow_score(context: dict[str, Any]) -> float:
    large_net = _safe_float(context.get("large_net")) or 0.0
    if large_net <= 0.0:
        return 0.35
    return _percent_rank(context.get("flow_rank"))


class BaseFactor:
    name: str = "base"
    weight: float = 0.0

    def compute(self, context: dict[str, Any]) -> FactorResult:
        raise NotImplementedError


class ThemeFactor(BaseFactor):
    name = "theme_strength"
    weight = 0.75

    def compute(self, context: dict[str, Any]) -> FactorResult:
        seed = _seed_score(context)
        binding = _binding_score(context)
        evidence_quality = _evidence_score(context)
        penalty = 0.08 if str(context.get("leader_tier") or "") == "证据不足候选" else 0.0
        raw_score = seed * 0.35 + binding * 0.20 + evidence_quality * 0.20 - penalty
        value = _clamp(raw_score / self.weight if self.weight else 0.0)
        return FactorResult(
            name=self.name,
            value=round(value, 6),
            weight=self.weight,
            score=round(value * self.weight, 6),
            evidence={
                "seed_score": round(seed * 100.0, 4),
                "binding_score": round(binding * 100.0, 4),
                "evidence_score": round(evidence_quality * 100.0, 4),
                "tier_penalty": round(penalty * 100.0, 4),
                "leader_tier": context.get("leader_tier"),
                "keyword_match": bool(context.get("keyword_match")),
            },
        )


class VolumeFactor(BaseFactor):
    name = "volume_activity"
    weight = 0.18

    def compute(self, context: dict[str, Any]) -> FactorResult:
        pct = _rescale(context.get("pct_chg"), -4.0, 10.0)
        turnover = _rescale(context.get("turnover_rate"), 1.0, 16.0)
        liquidity = _percent_rank(context.get("amount_rank"))
        limit = 1.0 if bool(context.get("is_limit_up")) else 0.45
        grouped = pct * 0.22 + turnover * 0.16 + liquidity * 0.20 + limit * 0.14
        value = _clamp(grouped / 0.72)
        return FactorResult(
            name=self.name,
            value=round(value, 6),
            weight=self.weight,
            score=round(value * self.weight, 6),
            evidence={
                "pct_chg_score": round(pct * 100.0, 4),
                "turnover_score": round(turnover * 100.0, 4),
                "liquidity_score": round(liquidity * 100.0, 4),
                "limit_score": round(limit * 100.0, 4),
                "amount_rank": _safe_float(context.get("amount_rank")),
                "turnover_rate": _safe_float(context.get("turnover_rate")),
                "pct_chg": _safe_float(context.get("pct_chg")),
            },
        )


class FundFlowFactor(BaseFactor):
    name = "fund_flow"
    weight = 0.055

    def compute(self, context: dict[str, Any]) -> FactorResult:
        flow = _flow_score(context)
        return FactorResult(
            name=self.name,
            value=round(flow, 6),
            weight=self.weight,
            score=round(flow * self.weight, 6),
            evidence={
                "flow_score": round(flow * 100.0, 4),
                "flow_rank": _safe_float(context.get("flow_rank")),
                "large_net": _safe_float(context.get("large_net")),
            },
        )


class CapQualityFactor(BaseFactor):
    name = "cap_quality"
    weight = 0.015

    def compute(self, context: dict[str, Any]) -> FactorResult:
        mv = _percent_rank(context.get("mv_rank"))
        return FactorResult(
            name=self.name,
            value=round(mv, 6),
            weight=self.weight,
            score=round(mv * self.weight, 6),
            evidence={
                "mv_score": round(mv * 100.0, 4),
                "mv_rank": _safe_float(context.get("mv_rank")),
                "total_mv": _safe_float(context.get("total_mv")),
            },
        )
