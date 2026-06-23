from __future__ import annotations

from leader_app import service


def stock_row(
    code: str,
    name: str,
    theme: str,
    rating: str,
    score: float,
    *,
    eligible: bool = True,
) -> dict:
    return {
        "code": code,
        "name": name,
        "xueqiu_url": f"https://xueqiu.com/S/{code[-2:]}{code[:6]}",
        "theme": theme,
        "deep_rating": rating,
        "deep_label": "可跟踪龙头" if rating == "A" else "核心确认" if rating == "S" else "观察股",
        "deep_score": score,
        "shadow_observation_eligible": eligible,
        "candidate_leader_tier": "证据确认龙头",
        "candidate_leader_claim": "样本龙头",
        "candidate_evidence_score": 86.0,
        "candidate_evidence_count": 4,
        "candidate_hard_evidence_count": 3,
        "market": {"pct_chg": 1.2},
        "scores": {"theme_binding": 80.0},
        "risk_flags": [],
        "data_gaps": [],
    }


def test_index_payload_exposes_primary_a_tracking_results(monkeypatch) -> None:
    stock_payload = {
        "schema_version": "stock_deep_research.v1",
        "report_id": "stock_deep_review_sample",
        "generated_at": "2026-06-23 12:10:05 CST",
        "basis_date": "2026-06-18",
        "summary": {"stock_count": 4, "eligible_count": 3},
        "stocks": [
            stock_row("688256.SH", "寒武纪", "硬科技电子/半导体", "A", 73.1),
            stock_row("688256.SH", "寒武纪", "AI算力/通信", "A", 73.1),
            stock_row("300750.SZ", "宁德时代", "新能源/电力设备", "A", 74.77),
            stock_row("688981.SH", "中芯国际", "硬科技电子/半导体", "B", 61.76, eligible=False),
        ],
        "shadow_contract": {},
        "data_gaps": [],
    }
    monkeypatch.setattr(service, "latest_stock_report", lambda: ("stock_deep_review_sample", stock_payload, "markdown"))
    monkeypatch.setattr(service, "list_stock_reports", lambda: [])
    monkeypatch.setattr(service, "list_reports", lambda: [])

    index = service.build_index_payload("leader_review_sample", {"themes": [], "data_gaps": []}, "")
    primary = index["key_results"]["primary_output"]

    assert index["page"]["primary_endpoint"] == "/api/index"
    assert index["page"]["primary_result_path"] == "key_results.primary_output.items"
    assert primary["id"] == "stock_deep_a_tracking_leaders"
    assert primary["count"] == 2
    assert [row["code"] for row in primary["items"]] == ["300750.SZ", "688256.SH"]
    cambricon = next(row for row in primary["items"] if row["code"] == "688256.SH")
    assert cambricon["theme"] == "AI算力/通信、硬科技电子/半导体"
    assert cambricon["themes"] == ["AI算力/通信", "硬科技电子/半导体"]
    assert index["key_results"]["integration"]["primary_data_path"] == "key_results.primary_output.items"
    assert index["key_results"]["integration"]["contains_trade_orders"] is False
