from __future__ import annotations

from pathlib import Path

from leader_app import research
from leader_app.pricing import PricePoint
from leader_app.service import build_index_payload, latest_report
from leader_app.upstream import parse_etf_candidates


def sample_theme_payload() -> dict:
    return {
        "report_id": "mainline_review_sample",
        "result": {
            "generated_at": "2026-06-22 15:34:51 CST",
            "basis_date": "2026-06-18",
            "nominal_today": "2026-06-22",
            "completeness": {"basis": "20260618"},
            "breadth": {"up_ratio": 36.7},
            "broad_indexes": [{"code": "000300.SH", "name": "沪深300", "r1": 0.2}],
            "theme_ranking": [
                {
                    "theme_id": "hard_tech_semiconductor",
                    "theme": "硬科技电子/半导体",
                    "stage": "次主线/强修复",
                    "lifecycle_state": "accelerating",
                    "evidence_score": 83.15,
                    "market_score": 89.05,
                    "policy_score": 49.66,
                    "mainline_score_v6": 0.4966,
                    "sw_score": 95.9,
                    "ths_score": 96.2,
                    "etf_score": 96.3,
                    "limit_count": 12,
                    "top_sw": "电子",
                    "top_ths": "半导体、元件",
                    "top_etf": "588200.SH 嘉实上证科创板芯片ETF、159995.SZ 华夏国证半导体芯片ETF",
                    "top_policy": "2026-06-03 国家发展改革委 发展智能经济新形态",
                },
                {
                    "theme_id": "building_materials",
                    "theme": "建材/稳增长修复",
                    "stage": "弱势/退潮",
                    "lifecycle_state": "dormant",
                    "evidence_score": 40,
                    "market_score": 42,
                    "policy_score": 10,
                    "etf_score": 30,
                    "top_etf": "",
                },
            ],
            "etf_top": [
                {
                    "ts_code": "588200.SH",
                    "name": "嘉实上证科创板芯片ETF",
                    "r1": 4.48,
                    "r5": 16.58,
                    "r20": 15.6,
                    "amount_rank": 0.99,
                    "score": 97.0,
                },
                {
                    "ts_code": "159995.SZ",
                    "name": "华夏国证半导体芯片ETF",
                    "r1": 4.68,
                    "r5": 17.38,
                    "r20": 13.68,
                    "amount_rank": 0.98,
                    "score": 96.5,
                },
            ],
        },
    }


def test_parse_etf_candidates() -> None:
    result = parse_etf_candidates("588200.SH 嘉实芯片ETF、159995.SZ 半导体ETF")

    assert [row["code"] for row in result] == ["588200.SH", "159995.SZ"]
    assert result[0]["name"] == "嘉实芯片ETF"


def test_build_report_and_shadow_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        research,
        "fetch_tushare_fund_prices",
        lambda codes, basis_date: {
            code: PricePoint(code=code, close=1.0, pct_chg=1.0, source="test", r5=5.0, r20=10.0, amount_rank=0.9)
            for code in codes
        },
    )
    monkeypatch.setattr(research, "_stock_universe", lambda basis_date: (None, ["stock data skipped"]))

    _report_id, payload, markdown = research.build_report(theme_payload=sample_theme_payload())

    assert payload["schema_version"] == "leader_research.v1"
    assert payload["basis_date"] == "2026-06-18"
    assert payload["themes"][0]["leader_grade"] in {"A", "B"}
    assert payload["themes"][0]["etf_leaders"][0]["code"] == "588200.SH"
    assert "stock data skipped" in payload["data_gaps"]
    assert "不含真实持仓、资金金额、股数或交易指令" in markdown

    shadow = payload["shadow_contract"]
    assert shadow["schema_version"] == "leader_shadow_input.v1"
    assert shadow["constraints"]["read_only"] is True
    assert shadow["constraints"]["ratio_only"] is True
    assert shadow["constraints"]["contains_trade_orders"] is False
    assert shadow["leader_signals"][0]["etf_candidates"][0]["code"] == "588200.SH"
    assert shadow["leader_signals"][0]["stock_candidates"] == []


def test_strategic_leader_universe_promotes_known_leaders(monkeypatch) -> None:
    import pandas as pd

    rows = pd.DataFrame(
        [
            {
                "ts_code": "688981.SH",
                "name": "中芯国际",
                "industry": "半导体",
                "market": "科创板",
                "pct_chg": 0.5,
                "turnover_rate": 2.0,
                "amount": 500000.0,
                "large_net": 100.0,
                "is_limit_up": False,
                "amount_rank": 0.75,
                "flow_rank": 0.7,
                "mv_rank": 0.98,
            },
            {
                "ts_code": "300308.SZ",
                "name": "中际旭创",
                "industry": "通信设备",
                "market": "创业板",
                "pct_chg": 1.2,
                "turnover_rate": 3.5,
                "amount": 800000.0,
                "large_net": 200.0,
                "is_limit_up": False,
                "amount_rank": 0.9,
                "flow_rank": 0.82,
                "mv_rank": 0.95,
            },
            {
                "ts_code": "300001.SZ",
                "name": "电子涨停样本",
                "industry": "半导体",
                "market": "创业板",
                "pct_chg": 20.0,
                "turnover_rate": 30.0,
                "amount": 900000.0,
                "large_net": 300.0,
                "is_limit_up": True,
                "amount_rank": 1.0,
                "flow_rank": 1.0,
                "mv_rank": 0.5,
            },
        ]
    )
    monkeypatch.setattr(
        research,
        "fetch_tushare_fund_prices",
        lambda codes, basis_date: {
            code: PricePoint(code=code, close=1.0, pct_chg=1.0, source="test", r5=5.0, r20=10.0, amount_rank=0.9)
            for code in codes
        },
    )
    monkeypatch.setattr(research, "_stock_universe", lambda basis_date: (rows, []))

    _report_id, payload, _markdown = research.build_report(theme_payload=sample_theme_payload())
    semiconductor_codes = [row["code"] for row in payload["themes"][0]["stock_leaders"]]

    assert "688981.SH" in semiconductor_codes
    smic = payload["themes"][0]["stock_leaders"][semiconductor_codes.index("688981.SH")]
    assert smic["binding_source"] == "候选种子+动态证据确认"
    assert smic["leader_tier"] == "证据确认龙头"
    assert smic["evidence_count"] >= 3
    assert smic["hard_evidence_count"] >= 2
    assert smic["score_model"] == "factorized_scoring_engine.v1"
    assert {row["name"] for row in smic["factor_breakdown"]} == {
        "theme_strength",
        "volume_activity",
        "fund_flow",
        "cap_quality",
    }
    assert payload["themes"][0]["stock_leaders"][0]["code"] == "688981.SH"


def test_report_service_uses_safe_latest_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        research,
        "fetch_tushare_fund_prices",
        lambda codes, basis_date: {
            code: PricePoint(code=code, close=1.0, pct_chg=1.0, source="test", r5=5.0, r20=10.0, amount_rank=0.9)
            for code in codes
        },
    )
    monkeypatch.setattr(research, "_stock_universe", lambda basis_date: (None, []))
    report_id, payload, markdown = research.build_report(theme_payload=sample_theme_payload())
    research.write_report(report_id, payload, markdown, report_dir=tmp_path)

    loaded_id, loaded_payload, loaded_markdown = latest_report(report_dir=tmp_path)
    index = build_index_payload(loaded_id, loaded_payload, loaded_markdown)

    assert loaded_id == report_id
    assert index["report"]["basis_date"] == "2026-06-18"
    assert index["metrics"]["etf_candidate_count"] >= 1
    assert index["shadow_contract"]["constraints"]["contains_cash_amounts"] is False
