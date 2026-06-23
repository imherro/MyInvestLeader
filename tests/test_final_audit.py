from __future__ import annotations

from leader_app.final_audit import build_final_audit_report
from core.scoring import build_theme_competition_graph


def stock(code: str, score: float, raw: float, liquidity: float, flow: float, pct: float) -> dict:
    return {
        "code": code,
        "name": code,
        "leader_score": score,
        "raw_factor_score": raw,
        "stock_lifecycle_state": "Expansion",
        "lifecycle_confidence": 0.9,
        "regime": "BULL_WEAK",
        "regime_multiplier": 1.0,
        "liquidity_rank": liquidity,
        "flow_rank": flow,
        "pct_chg": pct,
        "seed_score": 90.0,
        "evidence_score": 86.0,
        "evidence_count": 4,
        "hard_evidence_count": 3,
        "leader_tier": "证据确认龙头",
    }


def sample_payload() -> dict:
    theme = {
        "theme": "AI算力/通信",
        "stock_leaders": [
            stock("A", 98.0, 96.0, 0.95, 0.95, 5.0),
            stock("B", 96.0, 94.0, 0.90, 0.92, 4.0),
            stock("C", 92.0, 90.0, 0.80, 0.75, 3.0),
            stock("D", 88.0, 86.0, 0.70, 0.70, 2.0),
            stock("E", 84.0, 82.0, 0.60, 0.65, 1.0),
        ],
    }
    graph = build_theme_competition_graph(theme).to_dict()
    theme["competition_graph"] = graph
    for row in theme["stock_leaders"]:
        item = next(leader for leader in graph["leaders"] if leader["code"] == row["code"])
        row["ulls"] = item["ulls"]
    return {
        "report_id": "leader_review_sample",
        "basis_date": "2026-06-22",
        "themes": [theme],
        "competition_summary": {
            "theme_count": 1,
            "leader_swap_count": 0,
            "swap_frequency": {"before": 0.2, "after": 0.0},
            "rank_volatility": {"before": 0.2, "after": 0.1},
        },
    }


def test_build_final_audit_report() -> None:
    _audit_id, payload, markdown = build_final_audit_report(sample_payload())
    report = payload["FINAL_SYSTEM_AUDIT_REPORT"]

    assert payload["schema_version"] == "leader_final_audit.v1"
    assert payload["constraints"]["read_only"] is True
    assert report["sensitivity_score"] >= 0
    assert report["stability_score"] >= 0
    assert report["discriminability_score"] >= 0
    assert isinstance(report["system_risk_flags"], list)
    assert report["recommended_adjustments"]
    assert "FINAL_SYSTEM_AUDIT_REPORT" in markdown
