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
SYSTEM_NAME = "MyInvestLeader"
SYSTEM_VERSION = "0.1.0"
SYSTEM_DESCRIPTION = "A股主线龙头筛选、深研分析与影子仓位只读输入系统。"


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


def _unknown_current_status() -> dict[str, Any]:
    return {
        "current_status": "unknown",
        "current_status_label": "未判定",
        "current_status_detail": "未提供当前报告上下文，无法判断是否仍有效。",
    }


def _out_current_status() -> dict[str, Any]:
    return {
        "current_status": "out_current_pool",
        "current_status_label": "已出当前池",
        "current_status_detail": "最新A池、深研队列和候选矩阵均未包含。",
    }


def _candidate_current_status(row: dict[str, Any], *, theme: str = "") -> dict[str, Any]:
    tier = row.get("competition_tier") or row.get("tier") or row.get("candidate_leader_tier")
    detail = f"最新竞争层级 {tier}；未入最新A池。" if tier else "仍在最新候选矩阵；未入最新A池。"
    return {
        "current_status": "candidate_only",
        "current_status_label": "降为候选",
        "current_status_detail": detail,
        "current_theme": theme or row.get("theme") or "",
        "current_deep_rating": row.get("deep_rating"),
        "current_deep_label": row.get("deep_label"),
        "current_deep_score": row.get("deep_score"),
        "current_competition_tier": tier,
        "current_candidate_leader_tier": row.get("candidate_leader_tier") or row.get("leader_tier"),
        "current_candidate_leader_claim": row.get("candidate_leader_claim") or row.get("leader_claim"),
        "current_evidence_count": row.get("candidate_evidence_count") or row.get("evidence_count"),
        "current_hard_evidence_count": row.get("candidate_hard_evidence_count") or row.get("hard_evidence_count"),
    }


def _deep_current_status(row: dict[str, Any]) -> dict[str, Any]:
    rating = row.get("deep_rating") or ""
    label = row.get("deep_label") or ""
    if rating == "A":
        status = {
            "current_status": "current_a_tracking",
            "current_status_label": "仍在A池",
            "current_status_detail": "最新深研仍为A可跟踪龙头。",
        }
    else:
        status = {
            "current_status": "candidate_only",
            "current_status_label": "降为候选",
            "current_status_detail": f"最新深研为{rating} {label}；未入最新A池。".strip(),
        }
    status.update(
        {
            "current_theme": row.get("theme") or "",
            "current_deep_rating": rating,
            "current_deep_label": label,
            "current_deep_score": row.get("deep_score"),
            "current_competition_tier": row.get("competition_tier") or row.get("candidate_leader_tier"),
            "current_candidate_leader_tier": row.get("candidate_leader_tier"),
            "current_candidate_leader_claim": row.get("candidate_leader_claim"),
            "current_evidence_count": row.get("candidate_evidence_count"),
            "current_hard_evidence_count": row.get("candidate_hard_evidence_count"),
        }
    )
    return status


def _current_recommendation_status_by_code(stocks: list[dict[str, Any]], themes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    status_by_code: dict[str, dict[str, Any]] = {}
    for theme in themes:
        theme_name = str(theme.get("theme") or "")
        for row in theme.get("stock_leaders") or []:
            code = str(row.get("code") or "")
            if code:
                status_by_code[code] = _candidate_current_status(dict(row), theme=theme_name)
        graph = theme.get("competition_graph") or {}
        for row in graph.get("leaders") or []:
            code = str(row.get("code") or "")
            if code and code not in status_by_code:
                status_by_code[code] = _candidate_current_status(dict(row), theme=theme_name)
    for row in stocks:
        code = str(row.get("code") or "")
        if code and row.get("deep_rating") != "A":
            status_by_code[code] = _deep_current_status(dict(row))
    for row in _dedupe_stock_results(stocks, rating="A"):
        code = str(row.get("code") or "")
        if code:
            status_by_code[code] = _deep_current_status(dict(row))
    return status_by_code


def _with_current_status(item: dict[str, Any], current_status_by_code: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    code = str(item.get("code") or "")
    if current_status_by_code is None:
        status = _unknown_current_status()
    else:
        status = current_status_by_code.get(code) or _out_current_status()
    return {**item, **status}


def _current_status_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"current_a_tracking": 0, "candidate_only": 0, "out_current_pool": 0, "unknown": 0}
    for item in items:
        key = str(item.get("current_status") or "unknown")
        summary[key] = summary.get(key, 0) + 1
    return summary


def _recommendation_history_record(
    report_id: str,
    payload: dict[str, Any],
    *,
    has_markdown: bool = False,
    current_status_by_code: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stocks = [dict(row) for row in (payload.get("stocks") or [])]
    items = [_with_current_status(item, current_status_by_code) for item in _dedupe_stock_results(stocks, rating="A")]
    return {
        "report_id": report_id,
        "leader_report_id": payload.get("leader_report_id"),
        "generated_at": payload.get("generated_at"),
        "basis_date": payload.get("basis_date"),
        "count": len(items),
        "items": items,
        "codes": [row.get("code") for row in items if row.get("code")],
        "current_status_summary": _current_status_summary(items),
        "source_endpoint": f"/api/stocks/deep/reports/{report_id}",
        "markdown_endpoint": f"/api/stocks/deep/reports/{report_id}/markdown" if has_markdown else "",
        "has_markdown": has_markdown,
        "read_only": True,
        "contains_trade_orders": False,
    }


def list_recommendation_history(
    report_dir: Path = STOCK_REPORT_DIR,
    limit: int = 20,
    current_status_by_code: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_basis_dates: set[str] = set()
    for path in _stock_json_files(report_dir):
        payload = load_stock_report(path.stem, report_dir)
        basis_date = str(payload.get("basis_date") or path.stem)
        if basis_date in seen_basis_dates:
            continue
        seen_basis_dates.add(basis_date)
        records.append(
            _recommendation_history_record(
                path.stem,
                payload,
                has_markdown=path.with_suffix(".md").exists(),
                current_status_by_code=current_status_by_code,
            )
        )
        if len(records) >= limit:
            break
    return records


def list_current_recommendation_history(report_dir: Path = STOCK_REPORT_DIR, limit: int = 20) -> list[dict[str, Any]]:
    latest_stock = latest_stock_report()
    current_stocks = list((latest_stock[1].get("stocks") if latest_stock else []) or [])
    try:
        _report_id, leader_payload, _markdown = latest_report()
        current_themes = list(leader_payload.get("themes") or [])
    except HTTPException:
        current_themes = []
    return list_recommendation_history(
        report_dir=report_dir,
        limit=limit,
        current_status_by_code=_current_recommendation_status_by_code(current_stocks, current_themes),
    )


def _key_results_payload(stock_index: dict[str, Any] | None, themes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    stock_index = stock_index or {}
    report = stock_index.get("report") or {}
    stocks = [dict(row) for row in (stock_index.get("stocks") or [])]
    a_tracking = _dedupe_stock_results(stocks, rating="A")
    trackable = _dedupe_stock_results(stocks, eligible_only=True)
    current_status_by_code = _current_recommendation_status_by_code(stocks, themes or [])
    recommendation_history = list_recommendation_history(current_status_by_code=current_status_by_code)
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
        "recommendation_history": {
            "id": "daily_a_tracking_leader_history",
            "title": "每日推荐龙头历史",
            "description": "从历史龙头股深研报告抽取每个基准日的A可跟踪龙头；用于复核，不是交易指令。",
            "source_endpoint": "/api/stocks/deep/recommendations/history",
            "record_count": len(recommendation_history),
            "daily_latest_only": True,
            "records": recommendation_history,
        },
        "integration": {
            "endpoint": "/api/index",
            "primary_data_path": "key_results.primary_output.items",
            "history_data_path": "key_results.recommendation_history.records",
            "read_only": True,
            "ratio_only": True,
            "contains_trade_orders": False,
            "contains_cash_amounts": False,
            "contains_share_counts": False,
        },
        "process_flow": [
            {
                "step": 1,
                "title": "最早股票池",
                "data_source": "Tushare全A股票池 + 项目龙头种子库",
                "basis": "stock_basic、daily、daily_basic、moneyflow、limit_list_d，以及config/stock_leader_universe.json。",
                "pass_rule": "形成可研究的全A基础池；种子库只负责防漏，不直接给出最终结论。",
                "output_data_path": "internal.stock_universe",
            },
            {
                "step": 2,
                "title": "候选矩阵",
                "data_source": "主线关键词、行业映射、种子命中、主题角色门槛和动态行情证据",
                "basis": "候选必须满足种子命中，或关键词命中且主题角色匹配；再计算证据分、硬证据数和龙头分。",
                "pass_rule": "按leader_score、evidence_score、seed_score和成交额排序，保留动态前排候选；候选种子库和人工声明的细分龙头保底进入候选矩阵，但仍需后续竞争图谱和深研评分确认。",
                "output_data_path": "themes[].stock_leaders",
            },
            {
                "step": 3,
                "title": "竞争图谱",
                "data_source": "候选矩阵内的同主线股票",
                "basis": "综合基础因子、成交/流动性、资金流、动量、证据稳定性、生命周期和市场环境，计算ULLS。",
                "pass_rule": "按ULLS和证据资格分为L1、L2、L3、OUT；主题角色不匹配直接OUT，纯市场热点最高L3。",
                "output_data_path": "themes[].competition_graph.leaders",
            },
            {
                "step": 4,
                "title": "龙头股深研",
                "data_source": "A/B主线前排候选，以及短期弱主线里的证据确认龙头",
                "basis": "按主题绑定、财务质量、估值安全、交易结构和数据质量做单股深研评分。",
                "pass_rule": "输出S/A/B/C研究评级；风险标记、财务估值缺口和交易过热会压低评级。",
                "output_data_path": "stock_deep_research.stocks",
            },
            {
                "step": 5,
                "title": "A可跟踪龙头",
                "data_source": "龙头股深研结果",
                "basis": "取deep_rating=A的可跟踪龙头，按股票代码去重，保留所属主线、深研分、证据计数和风险缺口。",
                "pass_rule": "作为页面首屏关键成果和外部系统集成主输出；仍然只读，不是交易指令。",
                "output_data_path": "key_results.primary_output.items",
            },
        ],
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


def _catalog_endpoint(
    method: str,
    path: str,
    purpose: str,
    returns: str,
    *,
    params: list[dict[str, Any]] | None = None,
    read_only: bool = True,
) -> dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "purpose": purpose,
        "params": params or [],
        "returns": returns,
        "read_only": read_only,
    }


def build_api_catalog(base_url: str = "") -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    report_id_param = {
        "name": "report_id",
        "in": "path",
        "required": True,
        "description": "时间戳研究报告ID，例如 leader_review_YYYY-MM-DD_HHMMSS。",
    }
    stock_report_id_param = {
        "name": "report_id",
        "in": "path",
        "required": True,
        "description": "股票深研报告ID，例如 stock_deep_review_YYYY-MM-DD_HHMMSS。",
    }
    groups = [
        {
            "id": "docs",
            "title": "文档入口",
            "description": "系统首页、接口目录和自动生成的 OpenAPI 文档。",
            "endpoints": [
                _catalog_endpoint("GET", "/", "Web 首页，展示当前龙头研究关键结果。", "HTML 页面。"),
                _catalog_endpoint("GET", "/api", "统一接口目录，只返回说明，不读取研究文件或触发计算。", "接口目录 JSON。"),
                _catalog_endpoint("GET", "/docs", "FastAPI Swagger 文档。", "交互式 OpenAPI 文档页面。"),
                _catalog_endpoint("GET", "/redoc", "FastAPI ReDoc 文档。", "ReDoc 文档页面。"),
                _catalog_endpoint("GET", "/openapi.json", "OpenAPI 机器可读描述。", "OpenAPI JSON schema。"),
            ],
        },
        {
            "id": "current_data",
            "title": "当前数据",
            "description": "当前最新研究报告、深研结果和影子系统输入。",
            "endpoints": [
                _catalog_endpoint("GET", "/api/latest", "读取最新主线龙头研究 JSON。", "report_id 与完整 leader_research 结果。"),
                _catalog_endpoint("GET", "/api/shadow/latest", "读取最新影子仓位输入合约。", "leader_shadow_input 只读比例化信号。"),
                _catalog_endpoint("GET", "/api/stocks/deep/latest", "读取最新龙头股深研 JSON。", "report_id 与完整 stock_deep_research 结果。"),
                _catalog_endpoint("GET", "/api/stocks/deep/shadow/latest", "读取最新单股深研影子池输入。", "stock_deep_shadow_input 只读比例化信号。"),
            ],
        },
        {
            "id": "analysis_results",
            "title": "分析结果",
            "description": "页面主接口和跨系统集成首选入口。",
            "endpoints": [
                _catalog_endpoint(
                    "GET",
                    "/api/index",
                    "读取首页和外部集成所需的关键成果。",
                    "page、report、metrics、themes、key_results、stock_deep_research、shadow_contract 等。",
                ),
            ],
        },
        {
            "id": "history_data",
            "title": "历史数据",
            "description": "历史主线龙头报告、龙头股深研报告和每日A可跟踪龙头记录。",
            "endpoints": [
                _catalog_endpoint("GET", "/api/reports", "列出历史主线龙头研究报告。", "reports 数组。"),
                _catalog_endpoint(
                    "GET",
                    "/api/reports/{report_id}",
                    "读取指定主线龙头研究报告 JSON。",
                    "指定 report_id 的 leader_research 结果。",
                    params=[report_id_param],
                ),
                _catalog_endpoint(
                    "GET",
                    "/api/reports/{report_id}/markdown",
                    "读取指定主线龙头研究 Markdown。",
                    "text/markdown 文本。",
                    params=[report_id_param],
                ),
                _catalog_endpoint("GET", "/api/stocks/deep/reports", "列出历史龙头股深研报告。", "reports 数组。"),
                _catalog_endpoint(
                    "GET",
                    "/api/stocks/deep/reports/{report_id}",
                    "读取指定龙头股深研报告 JSON。",
                    "指定 report_id 的 stock_deep_research 结果。",
                    params=[stock_report_id_param],
                ),
                _catalog_endpoint(
                    "GET",
                    "/api/stocks/deep/reports/{report_id}/markdown",
                    "读取指定龙头股深研 Markdown。",
                    "text/markdown 文本。",
                    params=[stock_report_id_param],
                ),
                _catalog_endpoint(
                    "GET",
                    "/api/stocks/deep/recommendations/history",
                    "读取每日A可跟踪龙头历史记录。",
                    "records 数组，按基准日保留最近一次A可跟踪龙头清单。",
                ),
            ],
        },
        {
            "id": "system_status",
            "title": "系统状态",
            "description": "只读健康检查。",
            "endpoints": [
                _catalog_endpoint("GET", "/health", "系统健康检查和最新报告计数。", "ok、read_only、report_count、latest_report_id 等。"),
            ],
        },
    ]
    total_endpoints = sum(len(group["endpoints"]) for group in groups)
    return {
        "system": {
            "name": SYSTEM_NAME,
            "version": SYSTEM_VERSION,
            "description": SYSTEM_DESCRIPTION,
        },
        "base_url": normalized_base_url,
        "docs": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "swagger_url": f"{normalized_base_url}/docs" if normalized_base_url else "/docs",
            "redoc_url": f"{normalized_base_url}/redoc" if normalized_base_url else "/redoc",
            "openapi_url": f"{normalized_base_url}/openapi.json" if normalized_base_url else "/openapi.json",
        },
        "recommended_entrypoints": [
            {
                "path": "/api/index",
                "purpose": "首选集成入口，包含页面主要内容和A可跟踪龙头关键成果。",
                "data_path": "key_results.primary_output.items",
            },
            {
                "path": "/api/stocks/deep/latest",
                "purpose": "读取最新龙头股深研明细。",
                "data_path": "result.stocks",
            },
            {
                "path": "/api/stocks/deep/recommendations/history",
                "purpose": "复核每日A可跟踪龙头历史。",
                "data_path": "records",
            },
            {
                "path": "/api/shadow/latest",
                "purpose": "给影子仓位系统读取只读比例化主线信号。",
                "data_path": "leader_signals",
            },
        ],
        "safety": {
            "read_only": True,
            "no_recompute": True,
            "no_write": True,
            "no_trade_order": True,
            "ratio_only_for_shadow": True,
            "contains_cash_amounts": False,
            "contains_share_counts": False,
            "boundaries": [
                "/api 只返回接口说明，不触发研究重算、文件写入、交易、同步或外部调用。",
                "影子仓位相关接口只输出比例化研究信号，不包含真实资金、股数、下单指令或真实持仓写入。",
                "研究结论用于龙头筛选和分析，不等同于买卖建议。",
            ],
        },
        "groups": groups,
        "total_endpoints": total_endpoints,
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
                {
                    "id": "recommendation-history",
                    "title": "每日推荐龙头历史",
                    "data_path": "key_results.recommendation_history.records",
                },
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
        "key_results": _key_results_payload(stock_index, themes),
        "api_catalog": build_api_catalog(),
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
