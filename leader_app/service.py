from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .config import REPORT_DIR, STOCK_REPORT_DIR


REPORT_ID_RE = re.compile(r"^leader_review_\d{4}-\d{2}-\d{2}_\d{6}$")
STOCK_REPORT_ID_RE = re.compile(r"^stock_deep_review_\d{4}-\d{2}-\d{2}_\d{6}$")
KEY_RESULTS_SCHEMA_VERSION = "leader_index_key_results.v1"


def _json_files(report_dir: Path = REPORT_DIR) -> list[Path]:
    if not report_dir.exists():
        return []
    return sorted(report_dir.glob("leader_review_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _stock_json_files(report_dir: Path = STOCK_REPORT_DIR) -> list[Path]:
    if not report_dir.exists():
        return []
    return sorted(report_dir.glob("stock_deep_review_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _safe_path(report_id: str, suffix: str, report_dir: Path = REPORT_DIR) -> Path:
    if not REPORT_ID_RE.match(report_id):
        raise HTTPException(status_code=404, detail="研究报告不存在")
    path = report_dir / f"{report_id}{suffix}"
    if not path.exists() or path.parent != report_dir:
        raise HTTPException(status_code=404, detail="研究报告不存在")
    return path


def _safe_stock_path(report_id: str, suffix: str, report_dir: Path = STOCK_REPORT_DIR) -> Path:
    if not STOCK_REPORT_ID_RE.match(report_id):
        raise HTTPException(status_code=404, detail="股票深研报告不存在")
    path = report_dir / f"{report_id}{suffix}"
    if not path.exists() or path.parent != report_dir:
        raise HTTPException(status_code=404, detail="股票深研报告不存在")
    return path


def load_report(report_id: str, report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    path = _safe_path(report_id, ".json", report_dir)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"研究JSON无法解析: {path.name}") from exc


def load_markdown(report_id: str, report_dir: Path = REPORT_DIR) -> str:
    path = _safe_path(report_id, ".md", report_dir)
    return path.read_text(encoding="utf-8")


def load_stock_report(report_id: str, report_dir: Path = STOCK_REPORT_DIR) -> dict[str, Any]:
    path = _safe_stock_path(report_id, ".json", report_dir)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"股票深研JSON无法解析: {path.name}") from exc


def load_stock_markdown(report_id: str, report_dir: Path = STOCK_REPORT_DIR) -> str:
    path = _safe_stock_path(report_id, ".md", report_dir)
    return path.read_text(encoding="utf-8")


def latest_report(report_dir: Path = REPORT_DIR) -> tuple[str, dict[str, Any], str]:
    files = _json_files(report_dir)
    if not files:
        raise HTTPException(status_code=404, detail="还没有可读取的主线龙头研究结果，请先运行生成脚本")
    path = files[0]
    report_id = path.stem
    markdown = path.with_suffix(".md").read_text(encoding="utf-8") if path.with_suffix(".md").exists() else ""
    return report_id, load_report(report_id, report_dir), markdown


def latest_stock_report(report_dir: Path = STOCK_REPORT_DIR) -> tuple[str, dict[str, Any], str] | None:
    files = _stock_json_files(report_dir)
    if not files:
        return None
    path = files[0]
    report_id = path.stem
    markdown = path.with_suffix(".md").read_text(encoding="utf-8") if path.with_suffix(".md").exists() else ""
    return report_id, load_stock_report(report_id, report_dir), markdown


def list_reports(report_dir: Path = REPORT_DIR) -> list[dict[str, Any]]:
    reports = []
    for path in _json_files(report_dir):
        payload = load_report(path.stem, report_dir)
        summary = payload.get("leader_summary") or {}
        themes = payload.get("themes") or []
        reports.append(
            {
                "report_id": path.stem,
                "generated_at": payload.get("generated_at"),
                "basis_date": payload.get("basis_date"),
                "theme_report_id": (payload.get("upstream") or {}).get("theme_report_id"),
                "theme_count": summary.get("theme_count", len(themes)),
                "top_theme": summary.get("top_theme") or (themes[0].get("theme") if themes else ""),
                "top_grade": summary.get("top_grade") or (themes[0].get("leader_grade") if themes else ""),
                "data_gap_count": summary.get("data_gap_count", len(payload.get("data_gaps") or [])),
                "has_markdown": path.with_suffix(".md").exists(),
            }
        )
    return reports


def list_stock_reports(report_dir: Path = STOCK_REPORT_DIR) -> list[dict[str, Any]]:
    reports = []
    for path in _stock_json_files(report_dir):
        payload = load_stock_report(path.stem, report_dir)
        summary = payload.get("summary") or {}
        stocks = payload.get("stocks") or []
        reports.append(
            {
                "report_id": path.stem,
                "leader_report_id": payload.get("leader_report_id"),
                "generated_at": payload.get("generated_at"),
                "basis_date": payload.get("basis_date"),
                "stock_count": summary.get("stock_count", len(stocks)),
                "eligible_count": summary.get("eligible_count", 0),
                "top_stock": summary.get("top_stock") or (stocks[0].get("name") if stocks else ""),
                "data_gap_count": summary.get("data_gap_count", len(payload.get("data_gaps") or [])),
                "has_markdown": path.with_suffix(".md").exists(),
            }
        )
    return reports


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _compact_stock_result(row: dict[str, Any]) -> dict[str, Any]:
    theme = str(row.get("theme") or "")
    return {
        "code": row.get("code"),
        "name": row.get("name"),
        "xueqiu_url": row.get("xueqiu_url"),
        "theme": theme,
        "themes": [theme] if theme else [],
        "deep_rating": row.get("deep_rating"),
        "deep_label": row.get("deep_label"),
        "deep_score": row.get("deep_score"),
        "shadow_observation_eligible": bool(row.get("shadow_observation_eligible")),
        "candidate_leader_tier": row.get("candidate_leader_tier"),
        "candidate_leader_claim": row.get("candidate_leader_claim"),
        "candidate_evidence_score": row.get("candidate_evidence_score"),
        "candidate_evidence_count": row.get("candidate_evidence_count"),
        "candidate_hard_evidence_count": row.get("candidate_hard_evidence_count"),
        "market": row.get("market") or {},
        "scores": row.get("scores") or {},
        "risk_flags": row.get("risk_flags") or [],
        "data_gaps": row.get("data_gaps") or [],
    }


def _stock_result_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    rating_order = {"S": 0, "A": 1, "B": 2, "C": 3}
    return (
        rating_order.get(str(row.get("deep_rating") or ""), 9),
        -_num(row.get("deep_score")),
        str(row.get("code") or ""),
    )


def _dedupe_stock_results(stocks: list[dict[str, Any]], *, rating: str | None = None, eligible_only: bool = False) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    theme_sets: dict[str, set[str]] = {}
    for row in stocks:
        if rating is not None and row.get("deep_rating") != rating:
            continue
        if eligible_only and not row.get("shadow_observation_eligible"):
            continue
        code = str(row.get("code") or "")
        if not code:
            continue
        theme = str(row.get("theme") or "")
        current = _compact_stock_result(row)
        if code not in grouped or _stock_result_sort_key(current) < _stock_result_sort_key(grouped[code]):
            grouped[code] = current
        theme_sets.setdefault(code, set())
        if theme:
            theme_sets[code].add(theme)
    results = []
    for code, item in grouped.items():
        themes = sorted(theme_sets.get(code) or set())
        item["themes"] = themes
        item["theme"] = "、".join(themes) if themes else item.get("theme")
        results.append(item)
    return sorted(results, key=_stock_result_sort_key)


def _key_results_payload(stock_index: dict[str, Any] | None) -> dict[str, Any]:
    stock_index = stock_index or {}
    report = stock_index.get("report") or {}
    stocks = [dict(row) for row in (stock_index.get("stocks") or [])]
    a_tracking = _dedupe_stock_results(stocks, rating="A")
    trackable = _dedupe_stock_results(stocks, eligible_only=True)
    return {
        "schema_version": KEY_RESULTS_SCHEMA_VERSION,
        "primary_output": {
            "id": "stock_deep_a_tracking_leaders",
            "title": "龙头股深研 A可跟踪龙头",
            "description": "深研评级为A、可进入影子观察池的去重股票清单；只读研究结果，不是交易指令。",
            "source_endpoint": "/api/stocks/deep/latest",
            "source_report_id": report.get("report_id"),
            "count": len(a_tracking),
            "items": a_tracking,
        },
        "trackable_stock_leaders": {
            "id": "stock_deep_trackable_leaders",
            "title": "龙头股深研可跟踪池",
            "description": "shadow_observation_eligible=true 的去重股票清单，包含S/A评级。",
            "source_endpoint": "/api/stocks/deep/latest",
            "source_report_id": report.get("report_id"),
            "count": len(trackable),
            "items": trackable,
        },
        "integration": {
            "endpoint": "/api/index",
            "primary_data_path": "key_results.primary_output.items",
            "read_only": True,
            "ratio_only": True,
            "contains_trade_orders": False,
            "contains_cash_amounts": False,
            "contains_share_counts": False,
        },
    }


def _stock_index_payload() -> dict[str, Any] | None:
    latest = latest_stock_report()
    if latest is None:
        return None
    report_id, payload, markdown = latest
    return {
        "report": {
            "report_id": report_id,
            "schema_version": payload.get("schema_version"),
            "leader_report_id": payload.get("leader_report_id"),
            "generated_at": payload.get("generated_at"),
            "basis_date": payload.get("basis_date"),
            "data_gap_count": len(payload.get("data_gaps") or []),
        },
        "summary": payload.get("summary") or {},
        "stocks": payload.get("stocks") or [],
        "shadow_contract": payload.get("shadow_contract") or {},
        "data_gaps": payload.get("data_gaps") or [],
        "reports": list_stock_reports(),
        "markdown": markdown,
        "links": {
            "latest": "/api/stocks/deep/latest",
            "shadow": "/api/stocks/deep/shadow/latest",
            "reports": "/api/stocks/deep/reports",
        },
    }


def build_index_payload(report_id: str, payload: dict[str, Any], markdown: str) -> dict[str, Any]:
    themes = payload.get("themes") or []
    top_theme = themes[0] if themes else {}
    stock_index = _stock_index_payload()
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for theme in themes:
        grade = theme.get("leader_grade")
        if grade in grade_counts:
            grade_counts[grade] += 1
    return {
        "page": {
            "title": "MyInvestLeader",
            "subtitle": "A股主线龙头研究与影子仓位接口",
            "primary_endpoint": "/api/index",
            "primary_result_path": "key_results.primary_output.items",
            "sections": [
                {"id": "key-results", "title": "A可跟踪龙头", "data_path": "key_results.primary_output.items"},
                {"id": "metrics", "title": "研究概览", "data_path": "metrics"},
                {"id": "competition", "title": "主线竞争图谱", "data_path": "themes[].competition_graph"},
                {"id": "candidate-matrix", "title": "龙头候选矩阵", "data_path": "themes"},
                {"id": "stock-deep", "title": "龙头股深研", "data_path": "stock_deep_research.stocks"},
            ],
        },
        "report": {
            "report_id": report_id,
            "schema_version": payload.get("schema_version"),
            "generated_at": payload.get("generated_at"),
            "basis_date": payload.get("basis_date"),
            "theme_report_id": (payload.get("upstream") or {}).get("theme_report_id"),
            "theme_generated_at": (payload.get("upstream") or {}).get("theme_generated_at"),
            "top_theme": top_theme.get("theme", ""),
            "top_grade": top_theme.get("leader_grade", ""),
            "top_score": top_theme.get("leader_score"),
            "data_gap_count": len(payload.get("data_gaps") or []),
        },
        "metrics": {
            "theme_count": len(themes),
            "etf_candidate_count": sum(len(row.get("etf_leaders") or []) for row in themes),
            "stock_candidate_count": sum(len(row.get("stock_leaders") or []) for row in themes),
            "evidence_confirmed_stock_count": sum(
                1
                for theme in themes
                for row in (theme.get("stock_leaders") or [])
                if row.get("leader_tier") == "证据确认龙头"
            ),
            "grade_counts": grade_counts,
            "competition_summary": payload.get("competition_summary") or {},
        },
        "themes": themes,
        "competition_summary": payload.get("competition_summary") or {},
        "key_results": _key_results_payload(stock_index),
        "market_context": payload.get("market_context") or {},
        "market_regime": payload.get("market_regime") or {},
        "shadow_contract": payload.get("shadow_contract") or {},
        "data_gaps": payload.get("data_gaps") or [],
        "reports": list_reports(),
        "stock_deep_research": stock_index,
        "markdown": markdown,
        "links": {
            "latest": "/api/latest",
            "shadow": "/api/shadow/latest",
            "reports": "/api/reports",
            "stock_deep": "/api/stocks/deep/latest",
        },
    }


def latest_index_payload() -> dict[str, Any]:
    report_id, payload, markdown = latest_report()
    return build_index_payload(report_id, payload, markdown)
