from __future__ import annotations

import math
from typing import Any

from .normalization import percentile_rank
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

    def compute_raw(self, context: dict[str, Any]) -> float:
        raise NotImplementedError

    def comparison_contexts(self, context: dict[str, Any], universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return universe

    def absolute_value(self, context: dict[str, Any], raw_value: float) -> float:
        return _clamp(raw_value / 100.0, 0.0, 1.0)

    def normalize(self, context: dict[str, Any], raw_value: float, universe_values: list[float]) -> tuple[float, str]:
        if len(universe_values) < 2:
            return self.absolute_value(context, raw_value), "absolute_fallback"
        return percentile_rank(universe_values, raw_value), "percentile"

    def evidence(self, context: dict[str, Any], raw_value: float, value: float, mode: str) -> dict[str, Any]:
        return {
            "raw_value": round(raw_value, 6),
            "normalized_value": round(value, 6),
            "normalization": mode,
        }

    def compute(self, context: dict[str, Any], universe_values: list[float] | None = None) -> FactorResult:
        raw_value = self.compute_raw(context)
        value, mode = self.normalize(context, raw_value, universe_values or [])
        return FactorResult(
            name=self.name,
            value=round(value, 6),
            weight=self.weight,
            score=round(value * self.weight, 6),
            evidence=self.evidence(context, raw_value, value, mode),
        )


class ThemeFactor(BaseFactor):
    name = "theme_strength"
    weight = 0.75

    def compute_raw(self, context: dict[str, Any]) -> float:
        seed = _seed_score(context)
        binding = _binding_score(context)
        evidence_quality = _evidence_score(context)
        penalty = 0.08 if str(context.get("leader_tier") or "") == "证据不足候选" else 0.0
        raw_score = seed * 0.35 + binding * 0.20 + evidence_quality * 0.20 - penalty
        return raw_score * 100.0

    def absolute_value(self, context: dict[str, Any], raw_value: float) -> float:
        return _clamp(raw_value / (self.weight * 100.0), 0.0, 1.0)

    def evidence(self, context: dict[str, Any], raw_value: float, value: float, mode: str) -> dict[str, Any]:
        seed = _seed_score(context)
        binding = _binding_score(context)
        evidence_quality = _evidence_score(context)
        penalty = 0.08 if str(context.get("leader_tier") or "") == "证据不足候选" else 0.0
        return {
            "raw_value": round(raw_value, 6),
            "normalized_value": round(value, 6),
            "normalization": mode,
            "seed_score": round(seed * 100.0, 4),
            "binding_score": round(binding * 100.0, 4),
            "evidence_score": round(evidence_quality * 100.0, 4),
            "tier_penalty": round(penalty * 100.0, 4),
            "leader_tier": context.get("leader_tier"),
            "keyword_match": bool(context.get("keyword_match")),
        }


class VolumeFactor(BaseFactor):
    name = "volume_activity"
    weight = 0.18

    def _absolute_components(self, context: dict[str, Any]) -> dict[str, float]:
        pct = _rescale(context.get("pct_chg"), -4.0, 10.0)
        turnover = _rescale(context.get("turnover_rate"), 1.0, 16.0)
        liquidity = _percent_rank(context.get("amount_rank"))
        limit = 1.0 if bool(context.get("is_limit_up")) else 0.45
        return {
            "pct": pct,
            "turnover": turnover,
            "liquidity": liquidity,
            "limit": limit,
        }

    def compute_raw(self, context: dict[str, Any]) -> float:
        amount = _safe_float(context.get("amount"))
        if amount is not None and amount > 0.0:
            return math.log1p(amount)
        components = self._absolute_components(context)
        return (
            components["pct"] * 0.22
            + components["turnover"] * 0.16
            + components["liquidity"] * 0.20
            + components["limit"] * 0.14
        ) / 0.72 * 100.0

    def absolute_value(self, context: dict[str, Any], raw_value: float) -> float:
        components = self._absolute_components(context)
        grouped = (
            components["pct"] * 0.22
            + components["turnover"] * 0.16
            + components["liquidity"] * 0.20
            + components["limit"] * 0.14
        )
        return _clamp(grouped / 0.72)

    def evidence(self, context: dict[str, Any], raw_value: float, value: float, mode: str) -> dict[str, Any]:
        components = self._absolute_components(context)
        grouped = (
            components["pct"] * 0.22
            + components["turnover"] * 0.16
            + components["liquidity"] * 0.20
            + components["limit"] * 0.14
        )
        absolute_group_value = _clamp(grouped / 0.72)
        return {
            "raw_value": round(raw_value, 6),
            "normalized_value": round(value, 6),
            "normalization": mode,
            "absolute_group_value": round(absolute_group_value, 6),
            "pct_chg_score": round(components["pct"] * 100.0, 4),
            "turnover_score": round(components["turnover"] * 100.0, 4),
            "liquidity_score": round(components["liquidity"] * 100.0, 4),
            "limit_score": round(components["limit"] * 100.0, 4),
            "amount": _safe_float(context.get("amount")),
            "amount_rank": _safe_float(context.get("amount_rank")),
            "turnover_rate": _safe_float(context.get("turnover_rate")),
            "pct_chg": _safe_float(context.get("pct_chg")),
        }


class FundFlowFactor(BaseFactor):
    name = "fund_flow"
    weight = 0.055

    def comparison_contexts(self, context: dict[str, Any], universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
        industry = str(context.get("industry") or "")
        if not industry:
            return universe
        peers = [item for item in universe if str(item.get("industry") or "") == industry]
        return peers if len(peers) >= 3 else universe

    def compute_raw(self, context: dict[str, Any]) -> float:
        large_net = _safe_float(context.get("large_net"))
        if large_net is not None:
            return large_net
        return _flow_score(context) * 100.0

    def absolute_value(self, context: dict[str, Any], raw_value: float) -> float:
        return _flow_score(context)

    def evidence(self, context: dict[str, Any], raw_value: float, value: float, mode: str) -> dict[str, Any]:
        flow = _flow_score(context)
        return {
            "raw_value": round(raw_value, 6),
            "normalized_value": round(value, 6),
            "normalization": mode,
            "absolute_flow_score": round(flow * 100.0, 4),
            "flow_rank": _safe_float(context.get("flow_rank")),
            "large_net": _safe_float(context.get("large_net")),
            "industry": context.get("industry"),
        }


class CapQualityFactor(BaseFactor):
    name = "cap_quality"
    weight = 0.015

    def compute_raw(self, context: dict[str, Any]) -> float:
        total_mv = _safe_float(context.get("total_mv"))
        if total_mv is not None and total_mv > 0.0:
            return math.log1p(total_mv)
        return _percent_rank(context.get("mv_rank")) * 100.0

    def absolute_value(self, context: dict[str, Any], raw_value: float) -> float:
        return _percent_rank(context.get("mv_rank"))

    def evidence(self, context: dict[str, Any], raw_value: float, value: float, mode: str) -> dict[str, Any]:
        mv = _percent_rank(context.get("mv_rank"))
        return {
            "raw_value": round(raw_value, 6),
            "normalized_value": round(value, 6),
            "normalization": mode,
            "absolute_mv_score": round(mv * 100.0, 4),
            "mv_rank": _safe_float(context.get("mv_rank")),
            "total_mv": _safe_float(context.get("total_mv")),
        }
