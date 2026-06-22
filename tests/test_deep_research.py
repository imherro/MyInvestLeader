from __future__ import annotations

from pathlib import Path

from leader_app.deep_research import build_stock_deep_report, select_deep_queue, write_stock_deep_report
from leader_app.service import latest_stock_report, list_stock_reports


def sample_leader_payload() -> dict:
    return {
        "report_id": "leader_review_sample",
        "basis_date": "2026-06-18",
        "themes": [
            {
                "theme": "硬科技电子/半导体",
                "theme_id": "hard_tech_semiconductor",
                "stage": "次主线/强修复",
                "leader_grade": "B",
                "leader_score": 77.6,
                "lifecycle_state": "accelerating",
                "stock_leaders": [
                    {
                        "code": "600667.SH",
                        "name": "太极实业",
                        "industry": "半导体",
                        "grade": "A",
                        "leader_score": 99.03,
                        "pct_chg": 9.98,
                        "turnover_rate": 17.6,
                        "is_limit_up": True,
                        "flow_rank": 0.98,
                        "liquidity_rank": 0.99,
                        "binding_source": "候选种子+动态证据确认",
                        "leader_role": "半导体设备龙头",
                        "leader_claim": "半导体设备龙头",
                        "leader_tier": "证据确认龙头",
                        "strategic_score": 96,
                        "seed_score": 96,
                        "evidence_score": 82,
                        "evidence_count": 4,
                        "hard_evidence_count": 3,
                        "latest_evidence_date": "2026-06-18",
                        "evidence_sources": [
                            {
                                "type": "industry_role_seed",
                                "source_name": "config/stock_leader_universe.json",
                                "summary": "候选种子库标注：半导体设备龙头",
                                "confidence": 0.58,
                                "hard_evidence": False,
                            },
                            {
                                "type": "market_scale",
                                "source_name": "Tushare daily_basic.total_mv",
                                "summary": "总市值处于全A股前 5% 区间",
                                "confidence": 0.75,
                                "hard_evidence": True,
                            },
                        ],
                        "market_heat_score": 80,
                    },
                    {
                        "code": "688515.SH",
                        "name": "裕太微",
                        "industry": "半导体",
                        "grade": "A",
                        "leader_score": 94.64,
                        "pct_chg": 20.0,
                        "turnover_rate": 14.1,
                        "is_limit_up": True,
                        "flow_rank": 0.9,
                        "liquidity_rank": 0.95,
                    },
                ],
            },
            {
                "theme": "资源周期",
                "stage": "观察线",
                "leader_grade": "D",
                "leader_score": 40.9,
                "stock_leaders": [
                    {
                        "code": "600392.SH",
                        "name": "盛和资源",
                        "industry": "小金属",
                        "grade": "A",
                        "leader_score": 98.44,
                    }
                ],
            },
        ],
    }


def diagnostics() -> dict:
    return {
        "600667.SH": {
            "basic": {"name": "太极实业", "industry": "半导体"},
            "market": {"close": 9.88, "pct_chg": 9.98, "r5": 12.0, "r20": 18.0},
            "valuation": {"pe_ttm": 38.0, "pb": 2.8, "turnover_rate": 17.6},
            "financial": {
                "end_date": "20260331",
                "roe": 10.5,
                "grossprofit_margin": 22.0,
                "netprofit_margin": 8.0,
                "or_yoy": 18.0,
                "netprofit_yoy": 36.0,
                "debt_to_assets": 48.0,
                "ocf_to_or": 10.0,
            },
            "moneyflow": {"large_net": 1000.0},
            "risk_flags": [],
            "data_gaps": [],
        },
        "688515.SH": {
            "basic": {"name": "裕太微", "industry": "半导体"},
            "market": {"close": 120.0, "pct_chg": 20.0, "r5": 32.0, "r20": 50.0},
            "valuation": {"pe_ttm": 130.0, "pb": 13.0, "turnover_rate": 14.1},
            "financial": {},
            "moneyflow": {},
            "risk_flags": [],
            "data_gaps": ["缺少fina_indicator财务指标"],
        },
    }


def test_select_deep_queue_only_active_theme_grades() -> None:
    queue = select_deep_queue(sample_leader_payload(), max_per_theme=3)

    assert [row["code"] for row in queue] == ["600667.SH", "688515.SH"]
    assert all(row["theme_grade"] == "B" for row in queue)
    assert queue[0]["candidate_binding_source"] == "候选种子+动态证据确认"
    assert queue[0]["candidate_leader_tier"] == "证据确认龙头"


def test_build_stock_deep_report_contract() -> None:
    _report_id, payload, markdown = build_stock_deep_report(sample_leader_payload(), diagnostics=diagnostics())

    assert payload["schema_version"] == "stock_deep_research.v1"
    assert payload["constraints"]["research_first"] is True
    assert payload["constraints"]["contains_trade_orders"] is False
    assert payload["summary"]["stock_count"] == 2
    assert payload["stocks"][0]["code"] == "600667.SH"
    assert payload["stocks"][0]["deep_rating"] in {"S", "A", "B"}
    assert payload["stocks"][0]["candidate_leader_tier"] == "证据确认龙头"
    assert payload["stocks"][0]["candidate_hard_evidence_count"] == 3
    assert payload["stocks"][1]["deep_rating"] != "S"
    assert payload["shadow_contract"]["constraints"]["contains_cash_amounts"] is False
    assert payload["shadow_contract"]["stock_signals"][0]["code"] == "600667.SH"
    assert payload["shadow_contract"]["stock_signals"][0]["leader_tier"] == "证据确认龙头"
    assert "ResearchFirst" in markdown
    assert "证据链" in markdown


def test_stock_deep_service_reads_latest(tmp_path: Path) -> None:
    report_id, payload, markdown = build_stock_deep_report(sample_leader_payload(), diagnostics=diagnostics())
    write_stock_deep_report(report_id, payload, markdown, report_dir=tmp_path)

    latest = latest_stock_report(report_dir=tmp_path)
    reports = list_stock_reports(report_dir=tmp_path)

    assert latest is not None
    assert latest[0] == report_id
    assert reports[0]["stock_count"] == 2
    assert reports[0]["report_id"] == report_id
