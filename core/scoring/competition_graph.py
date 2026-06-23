from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .convergence import build_correlation_guard, calculate_ulls


@dataclass(frozen=True)
class CompetitionLeader:
    code: str
    name: str
    tier: str
    leadership_rank: int
    ulls: float
    raw_ulls: float
    leadership_score: float
    dominance: float
    normalized_theme_score: float
    relative_score_gap: float
    volume_share_in_theme: float
    fund_flow_share: float
    momentum_rank: int
    momentum_score: float
    leadership_stability: float
    persistence_score: float
    lifecycle_state: str
    regime: str
    convergence_explanations: dict[str, Any]
    correlation_guard: dict[str, Any]
    smoothed: bool
    previous_ulls: float | None
    competition_role: str
    reason: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThemeCompetitionGraph:
    theme: str
    candidate_set: list[str]
    leader_set: list[str]
    laggard_set: list[str]
    leaders: list[CompetitionLeader]
    competition_intensity: float
    leadership_stability: float
    current_l1: str | None
    score_top: str | None
    previous_l1: str | None
    leader_swap: bool
    leader_swap_reason: str
    score_top_displaced: bool
    rank_volatility: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["leaders"] = [leader.to_dict() for leader in self.leaders]
        return payload


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _share(values: list[float], index: int) -> float:
    total = sum(max(0.0, value) for value in values)
    if total <= 0:
        return round(1.0 / len(values), 4) if values else 0.0
    return _round(max(0.0, values[index]) / total)


def _relative_to_max(values: list[float], index: int) -> float:
    maximum = max(values) if values else 0.0
    if maximum <= 0:
        return 0.0
    return _clamp(values[index] / maximum)


def _momentum_rankings(stocks: list[dict[str, Any]]) -> dict[str, tuple[int, float]]:
    ranked = sorted(
        (
            (str(stock.get("code") or ""), _num(stock.get("pct_chg")))
            for stock in stocks
        ),
        key=lambda item: (-item[1], item[0]),
    )
    count = len(ranked)
    if count <= 1:
        return {code: (1, 1.0) for code, _value in ranked}
    return {
        code: (index, _clamp(1.0 - (index - 1) / (count - 1)))
        for index, (code, _value) in enumerate(ranked, start=1)
    }


def _rank_history_score(ranks: list[int], candidate_count: int) -> float | None:
    if not ranks:
        return None
    denominator = max(1, candidate_count - 1)
    scores = [_clamp(1.0 - (rank - 1) / denominator) for rank in ranks if rank > 0]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _persistence_score(
    stock: dict[str, Any],
    history_ranks: dict[str, list[int]],
    candidate_count: int,
) -> float:
    code = str(stock.get("code") or "")
    history_score = _rank_history_score(history_ranks.get(code, []), candidate_count)
    evidence_score = _clamp(_num(stock.get("evidence_score"), 50.0) / 100.0)
    evidence_count = max(1.0, _num(stock.get("evidence_count"), 0.0))
    hard_ratio = _clamp(_num(stock.get("hard_evidence_count"), 0.0) / evidence_count)
    seed_score = _clamp(_num(stock.get("seed_score"), 55.0) / 100.0)
    lifecycle_confidence = _clamp(_num(stock.get("lifecycle_confidence"), 0.5))
    tier = str(stock.get("leader_tier") or "")
    tier_score = 1.0 if tier == "证据确认龙头" else 0.72 if tier == "强候选龙头" else 0.52
    proxy = (
        evidence_score * 0.34
        + hard_ratio * 0.18
        + seed_score * 0.18
        + lifecycle_confidence * 0.18
        + tier_score * 0.12
    )
    if history_score is None:
        return _clamp(proxy)
    return _clamp(history_score * 0.58 + proxy * 0.42)


def _stock_reason(
    *,
    tier: str,
    dominance: float,
    lifecycle_state: str,
    momentum_rank: int,
    leadership_stability: float,
) -> list[str]:
    reasons = []
    if tier == "L1":
        reasons.append("ULLS ranks first after convergence smoothing")
    elif tier == "L2":
        reasons.append("secondary leader under converged ULLS")
    elif tier == "L3":
        reasons.append("follows the leading cluster but lacks top dominance")
    else:
        reasons.append("competition score or lifecycle state excludes leadership tier")
    if dominance >= 0.86:
        reasons.append("relative dominance is high inside the theme")
    if lifecycle_state in {"Breakout", "Expansion"}:
        reasons.append(f"lifecycle supports leadership: {lifecycle_state}")
    if lifecycle_state in {"Distribution", "Decline"}:
        reasons.append(f"lifecycle weakens leadership: {lifecycle_state}")
    if momentum_rank == 1:
        reasons.append("momentum rank is first in theme")
    if leadership_stability >= 0.75:
        reasons.append("persistence/stability evidence is strong")
    return reasons


def build_theme_competition_graph(
    theme: dict[str, Any],
    history_ranks: dict[str, list[int]] | None = None,
    previous_l1: str | None = None,
    previous_ulls: dict[str, float] | None = None,
) -> ThemeCompetitionGraph:
    stocks = [dict(row) for row in (theme.get("stock_leaders") or []) if row.get("code")]
    history_ranks = history_ranks or {}
    previous_ulls = previous_ulls or {}
    theme_name = str(theme.get("theme") or "")
    if not stocks:
        return ThemeCompetitionGraph(
            theme=theme_name,
            candidate_set=[],
            leader_set=[],
            laggard_set=[],
            leaders=[],
            competition_intensity=0.0,
            leadership_stability=0.0,
            current_l1=None,
            score_top=None,
            previous_l1=previous_l1,
            leader_swap=False,
            leader_swap_reason="no stock candidates",
            score_top_displaced=False,
            rank_volatility=0.0,
        )

    scores = [_num(stock.get("leader_score")) for stock in stocks]
    raw_scores = [_num(stock.get("raw_factor_score"), scores[index]) for index, stock in enumerate(stocks)]
    liquidity_values = [_num(stock.get("liquidity_rank"), 0.5) for stock in stocks]
    flow_values = [_num(stock.get("flow_rank"), 0.5) for stock in stocks]
    momentum = _momentum_rankings(stocks)
    candidate_count = len(stocks)
    interim: list[dict[str, Any]] = []

    for index, stock in enumerate(stocks):
        code = str(stock.get("code") or "")
        normalized_theme_score = _relative_to_max(scores, index)
        relative_score_gap = _clamp(1.0 - normalized_theme_score)
        volume_share = _share(liquidity_values, index)
        flow_share = _share(flow_values, index)
        volume_dominance = _relative_to_max(liquidity_values, index)
        flow_dominance = _relative_to_max(flow_values, index)
        momentum_rank, momentum_score = momentum.get(code, (candidate_count, 0.0))
        lifecycle_state = str(stock.get("stock_lifecycle_state") or "Accumulation")
        regime_multiplier = _num(stock.get("regime_multiplier"), 1.0)
        factor_component = _clamp(raw_scores[index] / 100.0)
        stability = _persistence_score(stock, history_ranks, candidate_count)
        dominance = _clamp(
            normalized_theme_score * 0.34
            + volume_dominance * 0.20
            + flow_dominance * 0.20
            + momentum_score * 0.18
            + stability * 0.08
        )
        interim.append(
            {
                "stock": stock,
                "code": code,
                "factor_component": factor_component,
                "normalized_theme_score": normalized_theme_score,
                "relative_score_gap": relative_score_gap,
                "volume_share": volume_share,
                "flow_share": flow_share,
                "momentum_rank": momentum_rank,
                "momentum_score": momentum_score,
                "dominance": dominance,
                "stability": stability,
                "lifecycle_state": lifecycle_state,
                "regime_multiplier": regime_multiplier,
                "regime": str(stock.get("regime") or ""),
            }
        )

    guard = build_correlation_guard(
        [row["factor_component"] for row in interim],
        [row["dominance"] for row in interim],
    )
    for row in interim:
        convergence = calculate_ulls(
            factor_score=row["factor_component"],
            lifecycle_state=row["lifecycle_state"],
            regime_multiplier=row["regime_multiplier"],
            dominance=row["dominance"],
            guard=guard,
            previous_ulls=previous_ulls.get(row["code"]),
        )
        row["convergence"] = convergence
        row["ulls"] = float(convergence.ulls)

    ranked = sorted(interim, key=lambda row: (-row["ulls"], row["code"]))
    leaders: list[CompetitionLeader] = []
    l2_budget = min(3, max(0, candidate_count - 1))
    l2_used = 0
    for rank, row in enumerate(ranked, start=1):
        lifecycle_state = row["lifecycle_state"]
        if rank == 1:
            tier = "L1"
        elif lifecycle_state == "Decline":
            tier = "OUT"
        elif lifecycle_state == "Distribution" and row["dominance"] < 0.78:
            tier = "OUT"
        elif l2_used < l2_budget and row["ulls"] >= 0.62:
            tier = "L2"
            l2_used += 1
        elif row["ulls"] >= 0.48 and row["relative_score_gap"] <= 0.42:
            tier = "L3"
        else:
            tier = "OUT"
        stock = row["stock"]
        convergence_payload = row["convergence"].to_dict()
        convergence_payload["tier"] = tier
        leaders.append(
            CompetitionLeader(
                code=row["code"],
                name=str(stock.get("name") or ""),
                tier=tier,
                leadership_rank=rank,
                ulls=_round(row["ulls"]),
                raw_ulls=_round(float(row["convergence"].raw_ulls)),
                leadership_score=_round(row["ulls"]),
                dominance=_round(row["dominance"]),
                normalized_theme_score=_round(row["normalized_theme_score"]),
                relative_score_gap=_round(row["relative_score_gap"]),
                volume_share_in_theme=_round(row["volume_share"]),
                fund_flow_share=_round(row["flow_share"]),
                momentum_rank=int(row["momentum_rank"]),
                momentum_score=_round(row["momentum_score"]),
                leadership_stability=_round(row["stability"]),
                persistence_score=_round(row["stability"]),
                lifecycle_state=lifecycle_state,
                regime=row["regime"],
                convergence_explanations=convergence_payload["explanations"],
                correlation_guard=convergence_payload["correlation_guard"],
                smoothed=bool(convergence_payload["smoothed"]),
                previous_ulls=convergence_payload["previous_ulls"],
                competition_role="explanatory_normalizer",
                reason=_stock_reason(
                    tier=tier,
                    dominance=row["dominance"],
                    lifecycle_state=lifecycle_state,
                    momentum_rank=int(row["momentum_rank"]),
                    leadership_stability=row["stability"],
                ),
            )
        )

    leader_set = [leader.code for leader in leaders if leader.tier in {"L1", "L2"}]
    laggard_set = [leader.code for leader in leaders if leader.tier == "OUT"]
    leadership_values = [leader.leadership_score for leader in leaders]
    if len(leadership_values) <= 1:
        competition_intensity = 0.0
    else:
        top = leadership_values[0]
        second = leadership_values[1]
        top3 = leadership_values[:3]
        top_gap = _clamp(top - second)
        top3_spread = _clamp(top - min(top3))
        crowding = _clamp(1.0 - (top_gap * 0.68 + top3_spread * 0.32) / 0.22)
        participation = _clamp(candidate_count / 8.0)
        volume_balance = _clamp(1.0 - max(_share(liquidity_values, idx) for idx in range(candidate_count)))
        competition_intensity = _clamp(crowding * 0.52 + participation * 0.28 + volume_balance * 0.20)

    top_stability = [leader.leadership_stability for leader in leaders[: min(3, len(leaders))]]
    leadership_stability = sum(top_stability) / len(top_stability) if top_stability else 0.0
    current_l1 = leaders[0].code if leaders else None
    score_top = str(stocks[0].get("code") or "") if stocks else None
    score_top_displaced = bool(current_l1 and score_top and current_l1 != score_top)
    historical_swap = bool(current_l1 and previous_l1 and current_l1 != previous_l1)
    leader_swap = historical_swap
    if historical_swap:
        leader_swap_reason = f"ULLS-smoothed L1 differs from previous L1 {previous_l1}"
    elif score_top_displaced:
        leader_swap_reason = f"ULLS L1 differs from raw score top {score_top}; treated as explanation, not swap"
    else:
        leader_swap_reason = "ULLS L1 aligns with previous/score context"
    movement = []
    denominator = max(1, candidate_count - 1)
    for leader in leaders:
        previous_rank = (history_ranks.get(leader.code) or [leader.leadership_rank])[0]
        movement.append(abs(leader.leadership_rank - previous_rank) / denominator)
    rank_volatility = sum(movement) / len(movement) if movement else 0.0

    return ThemeCompetitionGraph(
        theme=theme_name,
        candidate_set=[str(stock.get("code") or "") for stock in stocks],
        leader_set=leader_set,
        laggard_set=laggard_set,
        leaders=leaders,
        competition_intensity=_round(competition_intensity),
        leadership_stability=_round(leadership_stability),
        current_l1=current_l1,
        score_top=score_top,
        previous_l1=previous_l1,
        leader_swap=leader_swap,
        leader_swap_reason=leader_swap_reason,
        score_top_displaced=score_top_displaced,
        rank_volatility=_round(rank_volatility),
    )
