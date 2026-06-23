from __future__ import annotations

import json
import os

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
    monkeypatch.setattr(
        service,
        "list_recommendation_history",
        lambda *args, **kwargs: [
            {
                "report_id": "stock_deep_review_sample",
                "basis_date": "2026-06-18",
                "generated_at": "2026-06-23 12:10:05 CST",
                "count": 2,
                "items": [
                    stock_row("300750.SZ", "宁德时代", "新能源/电力设备", "A", 74.77),
                    stock_row("688256.SH", "寒武纪", "硬科技电子/半导体", "A", 73.1),
                ],
                "current_status_summary": {"current_a_tracking": 2},
            }
        ],
    )

    index = service.build_index_payload("leader_review_sample", {"themes": [], "data_gaps": []}, "")
    primary = index["key_results"]["primary_output"]
    history = index["key_results"]["recommendation_history"]

    assert index["page"]["primary_endpoint"] == "/api/index"
    assert index["page"]["primary_result_path"] == "key_results.primary_output.items"
    assert primary["id"] == "stock_deep_a_tracking_leaders"
    assert primary["count"] == 2
    assert [row["code"] for row in primary["items"]] == ["300750.SZ", "688256.SH"]
    cambricon = next(row for row in primary["items"] if row["code"] == "688256.SH")
    assert cambricon["theme"] == "AI算力/通信、硬科技电子/半导体"
    assert cambricon["themes"] == ["AI算力/通信", "硬科技电子/半导体"]
    assert index["key_results"]["integration"]["primary_data_path"] == "key_results.primary_output.items"
    assert index["key_results"]["integration"]["history_data_path"] == "key_results.recommendation_history.records"
    assert index["key_results"]["integration"]["contains_trade_orders"] is False
    assert history["record_count"] == 1
    assert history["records"][0]["basis_date"] == "2026-06-18"
    process_flow = index["key_results"]["process_flow"]
    assert [step["title"] for step in process_flow] == [
        "最早股票池",
        "候选矩阵",
        "竞争图谱",
        "龙头股深研",
        "A可跟踪龙头",
    ]
    assert process_flow[-1]["output_data_path"] == "key_results.primary_output.items"
    assert all(step["basis"] and step["pass_rule"] for step in process_flow)


def write_stock_report(path, *, basis_date: str, generated_at: str, stocks: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "stock_deep_research.v1",
                "leader_report_id": "leader_review_sample",
                "generated_at": generated_at,
                "basis_date": basis_date,
                "stocks": stocks,
                "data_gaps": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_recommendation_history_keeps_latest_report_per_basis_date(tmp_path) -> None:
    old_same_day = tmp_path / "stock_deep_review_2026-06-19_090000.json"
    latest_same_day = tmp_path / "stock_deep_review_2026-06-19_153000.json"
    next_day = tmp_path / "stock_deep_review_2026-06-20_090000.json"

    write_stock_report(
        old_same_day,
        basis_date="2026-06-18",
        generated_at="2026-06-19 09:00:00 CST",
        stocks=[stock_row("688256.SH", "寒武纪", "硬科技电子/半导体", "A", 70.0)],
    )
    write_stock_report(
        latest_same_day,
        basis_date="2026-06-18",
        generated_at="2026-06-19 15:30:00 CST",
        stocks=[stock_row("300750.SZ", "宁德时代", "新能源/电力设备", "A", 74.0)],
    )
    latest_same_day.with_suffix(".md").write_text("# 深研", encoding="utf-8")
    write_stock_report(
        next_day,
        basis_date="2026-06-19",
        generated_at="2026-06-20 09:00:00 CST",
        stocks=[
            stock_row("688981.SH", "中芯国际", "硬科技电子/半导体", "A", 76.0),
            stock_row("000063.SZ", "中兴通讯", "AI算力/通信", "B", 62.0),
        ],
    )

    os.utime(old_same_day, (1_800_000_000, 1_800_000_000))
    os.utime(latest_same_day, (1_800_000_100, 1_800_000_100))
    os.utime(next_day, (1_800_000_200, 1_800_000_200))

    records = service.list_recommendation_history(report_dir=tmp_path)

    assert [record["basis_date"] for record in records] == ["2026-06-19", "2026-06-18"]
    assert records[0]["codes"] == ["688981.SH"]
    assert records[1]["codes"] == ["300750.SZ"]
    assert records[1]["has_markdown"] is True
    assert records[0]["read_only"] is True
    assert records[0]["contains_trade_orders"] is False
    assert records[0]["items"][0]["current_status"] == "unknown"


def test_recommendation_history_marks_current_status(tmp_path) -> None:
    history_path = tmp_path / "stock_deep_review_2026-06-19_153000.json"
    write_stock_report(
        history_path,
        basis_date="2026-06-18",
        generated_at="2026-06-19 15:30:00 CST",
        stocks=[
            stock_row("688256.SH", "寒武纪", "AI算力/通信", "A", 74.0),
            stock_row("300308.SZ", "中际旭创", "AI算力/通信", "A", 72.0),
            stock_row("688981.SH", "中芯国际", "硬科技电子/半导体", "A", 70.0),
        ],
    )
    current_status_by_code = service._current_recommendation_status_by_code(
        stocks=[stock_row("688256.SH", "寒武纪", "AI算力/通信", "A", 73.1)],
        themes=[
            {
                "theme": "AI算力/通信",
                "stock_leaders": [
                    {
                        "code": "300308.SZ",
                        "name": "中际旭创",
                        "competition_tier": "L3",
                        "leader_tier": "证据确认龙头",
                        "leader_claim": "高速光模块龙头",
                        "evidence_count": 4,
                        "hard_evidence_count": 3,
                    }
                ],
            }
        ],
    )

    records = service.list_recommendation_history(
        report_dir=tmp_path,
        current_status_by_code=current_status_by_code,
    )
    items = {row["code"]: row for row in records[0]["items"]}

    assert items["688256.SH"]["current_status_label"] == "仍在A池"
    assert items["300308.SZ"]["current_status_label"] == "降为候选"
    assert items["300308.SZ"]["current_competition_tier"] == "L3"
    assert items["688981.SH"]["current_status_label"] == "已出当前池"
    assert records[0]["current_status_summary"] == {
        "current_a_tracking": 1,
        "candidate_only": 1,
        "out_current_pool": 1,
        "unknown": 0,
    }
