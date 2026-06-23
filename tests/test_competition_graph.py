from __future__ import annotations

from core.scoring import build_theme_competition_graph


def stock(
    code: str,
    score: float,
    raw: float,
    lifecycle: str,
    liquidity: float,
    flow: float,
    pct: float,
    seed: float | None = 90.0,
) -> dict:
    return {
        "code": code,
        "name": code,
        "leader_score": score,
        "raw_factor_score": raw,
        "stock_lifecycle_state": lifecycle,
        "lifecycle_confidence": 0.85,
        "regime": "BULL_WEAK",
        "regime_multiplier": 1.0,
        "liquidity_rank": liquidity,
        "flow_rank": flow,
        "pct_chg": pct,
        "seed_score": seed,
        "evidence_score": 86.0,
        "evidence_count": 4,
        "hard_evidence_count": 3,
        "leader_tier": "证据确认龙头" if seed else "市场热点候选",
    }


def test_theme_competition_graph_assigns_unique_l1_and_out() -> None:
    theme = {
        "theme": "AI算力/通信",
        "stock_leaders": [
            stock("A", 96.0, 95.0, "Expansion", 0.95, 0.90, 5.0),
            stock("B", 94.0, 93.0, "Breakout", 0.90, 0.88, 6.0),
            stock("C", 90.0, 90.0, "Accumulation", 0.60, 0.50, 1.0),
            stock("D", 72.0, 80.0, "Distribution", 0.80, 0.10, -0.5, None),
        ],
    }

    graph = build_theme_competition_graph(theme).to_dict()
    tiers = [row["tier"] for row in graph["leaders"]]

    assert tiers.count("L1") == 1
    assert graph["leader_set"]
    assert graph["competition_intensity"] > 0
    assert graph["leadership_stability"] > 0
    assert graph["leaders"][0]["ulls"] == graph["leaders"][0]["leadership_score"]
    assert graph["leaders"][0]["competition_role"] == "explanatory_normalizer"
    assert any(row["tier"] == "OUT" and row["code"] == "D" for row in graph["leaders"])
    assert {"relative_score_gap", "volume_share_in_theme", "fund_flow_share", "momentum_rank"}.issubset(
        graph["leaders"][0]
    )


def test_competition_graph_can_displace_score_top() -> None:
    theme = {
        "theme": "新能源/电力设备",
        "stock_leaders": [
            stock("SCORE_TOP", 100.0, 95.0, "Distribution", 0.60, 0.12, -1.0),
            stock("COMPETITION_L1", 92.0, 92.0, "Expansion", 1.00, 1.00, 8.0),
            stock("FOLLOWER", 88.0, 88.0, "Accumulation", 0.70, 0.65, 2.0),
        ],
    }

    graph = build_theme_competition_graph(theme, previous_l1="SCORE_TOP").to_dict()

    assert graph["current_l1"] == "COMPETITION_L1"
    assert graph["score_top"] == "SCORE_TOP"
    assert graph["score_top_displaced"] is True
    assert graph["leader_swap"] is True
    assert "previous L1" in graph["leader_swap_reason"]
