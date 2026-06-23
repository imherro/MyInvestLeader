from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.scoring import build_theme_competition_graph

from .config import AUDIT_REPORT_DIR
from .pricing import safe_float
from .research import TZ


SCHEMA_VERSION = "leader_final_audit.v1"
PERTURBATION_LEVELS = (0.05, 0.10, 0.15)


def _now_audit_id() -> str:
    return f"final_audit_{datetime.now(TZ).strftime('%Y-%m-%d_%H%M%S')}"


def _round(value: Any, digits: int = 4) -> float:
    number = safe_float(value)
    if number is None:
        return 0.0
    return round(float(number), digits)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _leader_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("code") or ""): row for row in graph.get("leaders") or [] if row.get("code")}


def _previous_ulls(graph: dict[str, Any]) -> dict[str, float]:
    values = {}
    for row in graph.get("leaders") or []:
        score = safe_float(row.get("ulls"))
        if row.get("code") and score is not None:
            values[str(row.get("code"))] = float(score)
    return values


def _rebuild_graph(theme: dict[str, Any], base_graph: dict[str, Any]) -> dict[str, Any]:
    return build_theme_competition_graph(
        theme,
        previous_l1=base_graph.get("current_l1"),
        previous_ulls=_previous_ulls(base_graph),
    ).to_dict()


def _stock_by_code(theme: dict[str, Any], code: str) -> dict[str, Any] | None:
    for stock in theme.get("stock_leaders") or []:
        if str(stock.get("code") or "") == code:
            return stock
    return None


def _challenger_code(graph: dict[str, Any]) -> str | None:
    leaders = graph.get("leaders") or []
    if len(leaders) >= 2:
        return str(leaders[1].get("code") or "")
    if leaders:
        return str(leaders[0].get("code") or "")
    return None


def _perturb_stock(stock: dict[str, Any], signal: str, level: float) -> None:
    if signal == "volume":
        stock["liquidity_rank"] = min(1.0, _round((safe_float(stock.get("liquidity_rank")) or 0.0) * (1.0 + level), 6))
    elif signal == "fund_flow":
        stock["flow_rank"] = min(1.0, _round((safe_float(stock.get("flow_rank")) or 0.0) * (1.0 + level), 6))
    elif signal == "theme_strength":
        stock["raw_factor_score"] = min(100.0, _round((safe_float(stock.get("raw_factor_score")) or 0.0) * (1.0 + level), 6))


def sensitivity_audit(payload: dict[str, Any]) -> dict[str, Any]:
    scenarios = []
    for theme in payload.get("themes") or []:
        base_graph = theme.get("competition_graph") or {}
        base_leaders = _leader_map(base_graph)
        target = _challenger_code(base_graph)
        if not target or target not in base_leaders:
            continue
        base_target = base_leaders[target]
        for signal in ("volume", "fund_flow", "theme_strength"):
            for level in PERTURBATION_LEVELS:
                scenario_theme = copy.deepcopy(theme)
                target_stock = _stock_by_code(scenario_theme, target)
                if not target_stock:
                    continue
                _perturb_stock(target_stock, signal, level)
                graph = _rebuild_graph(scenario_theme, base_graph)
                leaders = _leader_map(graph)
                after_target = leaders.get(target) or {}
                before_ulls = safe_float(base_target.get("ulls")) or 0.0
                after_ulls = safe_float(after_target.get("ulls")) or before_ulls
                before_rank = int(safe_float(base_target.get("leadership_rank")) or 0)
                after_rank = int(safe_float(after_target.get("leadership_rank")) or before_rank)
                scenarios.append(
                    {
                        "theme": theme.get("theme"),
                        "signal": signal,
                        "level": level,
                        "target": target,
                        "ulls_change_rate": _round(abs(after_ulls - before_ulls) / before_ulls if before_ulls else 0.0, 6),
                        "l1_changed": graph.get("current_l1") != base_graph.get("current_l1"),
                        "rank_change": before_rank - after_rank,
                    }
                )
    avg_change = sum(row["ulls_change_rate"] for row in scenarios) / len(scenarios) if scenarios else 0.0
    rank_change_rate = sum(1 for row in scenarios if row["rank_change"] != 0) / len(scenarios) if scenarios else 0.0
    l1_change_rate = sum(1 for row in scenarios if row["l1_changed"]) / len(scenarios) if scenarios else 0.0
    score = _clamp((min(avg_change / 0.035, 1.0) * 0.45 + min(rank_change_rate / 0.30, 1.0) * 0.35 + min(l1_change_rate / 0.12, 1.0) * 0.20) * 100.0)
    return {
        "sensitivity_score": _round(score, 2),
        "average_ulls_change_rate": _round(avg_change, 6),
        "rank_change_rate": _round(rank_change_rate, 6),
        "l1_change_rate": _round(l1_change_rate, 6),
        "scenarios": scenarios,
    }


def _regime_scenario(theme: dict[str, Any], multiplier: float) -> dict[str, Any]:
    result = copy.deepcopy(theme)
    for stock in result.get("stock_leaders") or []:
        stock["regime_multiplier"] = multiplier
    return result


def _lifecycle_scenario(theme: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(theme)
    graph = result.get("competition_graph") or {}
    l1 = graph.get("current_l1")
    stock = _stock_by_code(result, str(l1 or ""))
    if stock and stock.get("stock_lifecycle_state") == "Expansion":
        stock["stock_lifecycle_state"] = "Breakout"
    return result


def _factor_noise_scenario(theme: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(theme)
    for index, stock in enumerate(result.get("stock_leaders") or []):
        factor = 1.02 if index % 2 == 0 else 0.98
        stock["raw_factor_score"] = min(100.0, _round((safe_float(stock.get("raw_factor_score")) or 0.0) * factor, 6))
    return result


def stability_audit(payload: dict[str, Any]) -> dict[str, Any]:
    scenarios = []
    for theme in payload.get("themes") or []:
        base_graph = theme.get("competition_graph") or {}
        base_leaders = _leader_map(base_graph)
        scenario_builders = {
            "regime_to_sideways": lambda item: _regime_scenario(item, 0.85),
            "regime_to_bull_strong": lambda item: _regime_scenario(item, 1.10),
            "lifecycle_minor_downgrade": _lifecycle_scenario,
            "factor_noise_2pct": _factor_noise_scenario,
        }
        for name, builder in scenario_builders.items():
            scenario_theme = builder(theme)
            graph = _rebuild_graph(scenario_theme, base_graph)
            leaders = _leader_map(graph)
            deltas = []
            for code, before in base_leaders.items():
                after = leaders.get(code) or {}
                before_ulls = safe_float(before.get("ulls")) or 0.0
                after_ulls = safe_float(after.get("ulls")) or before_ulls
                if before_ulls:
                    deltas.append(abs(after_ulls - before_ulls) / before_ulls)
            scenarios.append(
                {
                    "theme": theme.get("theme"),
                    "scenario": name,
                    "l1_changed": graph.get("current_l1") != base_graph.get("current_l1"),
                    "average_ulls_change_rate": _round(sum(deltas) / len(deltas) if deltas else 0.0, 6),
                }
            )
    l1_change_rate = sum(1 for row in scenarios if row["l1_changed"]) / len(scenarios) if scenarios else 0.0
    avg_ulls_change = sum(row["average_ulls_change_rate"] for row in scenarios) / len(scenarios) if scenarios else 0.0
    regime_effects = [row["average_ulls_change_rate"] for row in scenarios if row["scenario"].startswith("regime")]
    score = _clamp((1.0 - l1_change_rate) * 75.0 + min(avg_ulls_change / 0.035, 1.0) * 25.0)
    return {
        "stability_score": _round(score, 2),
        "l1_change_rate": _round(l1_change_rate, 6),
        "average_ulls_change_rate": _round(avg_ulls_change, 6),
        "regime_effect_rate": _round(sum(regime_effects) / len(regime_effects) if regime_effects else 0.0, 6),
        "scenarios": scenarios,
    }


def discriminability_audit(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for theme in payload.get("themes") or []:
        leaders = theme.get("competition_graph", {}).get("leaders") or []
        if len(leaders) < 2:
            continue
        top1 = safe_float(leaders[0].get("ulls")) or 0.0
        top2 = safe_float(leaders[1].get("ulls")) or top1
        top5 = safe_float(leaders[min(4, len(leaders) - 1)].get("ulls")) or top1
        rows.append(
            {
                "theme": theme.get("theme"),
                "l1_l2_gap": _round(top1 - top2, 6),
                "top1_top5_gap": _round(top1 - top5, 6),
                "score_cluster_flattening": (top1 - top5) < 0.05,
            }
        )
    avg_l1_l2 = sum(row["l1_l2_gap"] for row in rows) / len(rows) if rows else 0.0
    avg_top5 = sum(row["top1_top5_gap"] for row in rows) / len(rows) if rows else 0.0
    flatten_rate = sum(1 for row in rows if row["score_cluster_flattening"]) / len(rows) if rows else 0.0
    score = _clamp((min(avg_l1_l2 / 0.035, 1.0) * 0.35 + min(avg_top5 / 0.085, 1.0) * 0.45 + (1.0 - flatten_rate) * 0.20) * 100.0)
    return {
        "discriminability_score": _round(score, 2),
        "average_l1_l2_gap": _round(avg_l1_l2, 6),
        "average_top1_top5_gap": _round(avg_top5, 6),
        "score_cluster_flattening_rate": _round(flatten_rate, 6),
        "themes": rows,
    }


def _risk_flags(sensitivity: dict[str, Any], stability: dict[str, Any], discriminability: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    flags = []
    swap_after = safe_float((summary.get("swap_frequency") or {}).get("after")) or 0.0
    rank_after = safe_float((summary.get("rank_volatility") or {}).get("after")) or 0.0
    if swap_after == 0.0 and rank_after < 0.20:
        flags.append("over_smoothing_risk")
    elif swap_after == 0.0:
        flags.append("over_smoothing_watch")
    if (discriminability.get("average_top1_top5_gap") or 0.0) < 0.05 or (discriminability.get("score_cluster_flattening_rate") or 0.0) >= 0.40:
        flags.append("under_separation_risk")
    if (stability.get("regime_effect_rate") or 0.0) < 0.03:
        flags.append("regime_nullification_risk")
    if (sensitivity.get("l1_change_rate") or 0.0) == 0.0 and (sensitivity.get("average_ulls_change_rate") or 0.0) < 0.015:
        flags.append("lagging_detection_risk")
    return flags


def _recommended_adjustments(flags: list[str]) -> list[str]:
    recommendations = []
    if "over_smoothing_risk" in flags or "over_smoothing_watch" in flags:
        recommendations.append("Do not roll back smoothing immediately; monitor one more report and consider changing smoothing from 0.7/0.3 to 0.8/0.2 if swap remains zero.")
    if "under_separation_risk" in flags:
        recommendations.append("Increase L1/L2 separation discipline in reporting: flag themes where top1-top5 ULLS gap stays below 0.05 instead of forcing a stronger conclusion.")
    if "regime_nullification_risk" in flags:
        recommendations.append("Slightly raise regime explanatory visibility; keep it as a modifier, but audit whether 0.10 regime weight is too low in BEAR/SIDEWAYS snapshots.")
    if "lagging_detection_risk" in flags:
        recommendations.append("Add a watch-only early-breakout warning when 15% perturbations improve challenger rank but do not change L1; do not change trading behavior.")
    if not recommendations:
        recommendations.append("Keep current ULLS, correlation guard, and smoothing weights; continue report-by-report monitoring.")
    return recommendations


def build_final_audit_report(leader_payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    audit_id = _now_audit_id()
    sensitivity = sensitivity_audit(leader_payload)
    stability = stability_audit(leader_payload)
    discriminability = discriminability_audit(leader_payload)
    competition_summary = leader_payload.get("competition_summary") or {}
    flags = _risk_flags(sensitivity, stability, discriminability, competition_summary)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": audit_id,
        "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S CST"),
        "leader_report_id": leader_payload.get("report_id"),
        "basis_date": leader_payload.get("basis_date"),
        "constraints": {
            "read_only": True,
            "no_trade_order": True,
            "no_new_factor": True,
            "no_ml": True,
        },
        "FINAL_SYSTEM_AUDIT_REPORT": {
            "sensitivity_score": sensitivity["sensitivity_score"],
            "stability_score": stability["stability_score"],
            "discriminability_score": discriminability["discriminability_score"],
            "system_risk_flags": flags,
            "recommended_adjustments": _recommended_adjustments(flags),
        },
        "audits": {
            "sensitivity": sensitivity,
            "stability": stability,
            "discriminability": discriminability,
        },
        "competition_summary": competition_summary,
    }
    return audit_id, payload, render_final_audit_markdown(payload)


def render_final_audit_markdown(payload: dict[str, Any]) -> str:
    report = payload.get("FINAL_SYSTEM_AUDIT_REPORT") or {}
    audits = payload.get("audits") or {}
    sensitivity = audits.get("sensitivity") or {}
    stability = audits.get("stability") or {}
    discriminability = audits.get("discriminability") or {}
    lines = [
        f"# 龙头系统最终校准审计：{payload.get('basis_date')}",
        "",
        f"- 审计ID：{payload.get('audit_id')}",
        f"- 主线报告：{payload.get('leader_report_id')}",
        "- 约束：只读审计；不新增因子；不引入 ML；不输出交易指令。",
        "",
        "## FINAL_SYSTEM_AUDIT_REPORT",
        "",
        f"- sensitivity_score：{report.get('sensitivity_score')}",
        f"- stability_score：{report.get('stability_score')}",
        f"- discriminability_score：{report.get('discriminability_score')}",
        f"- system_risk_flags：{', '.join(report.get('system_risk_flags') or []) or 'none'}",
        "",
        "## Recommended Adjustments",
        "",
    ]
    lines.extend(f"- {item}" for item in report.get("recommended_adjustments") or [])
    lines += [
        "",
        "## Sensitivity Audit",
        "",
        f"- average_ulls_change_rate：{sensitivity.get('average_ulls_change_rate')}",
        f"- rank_change_rate：{sensitivity.get('rank_change_rate')}",
        f"- l1_change_rate：{sensitivity.get('l1_change_rate')}",
        "",
        "## Stability Audit",
        "",
        f"- average_ulls_change_rate：{stability.get('average_ulls_change_rate')}",
        f"- regime_effect_rate：{stability.get('regime_effect_rate')}",
        f"- l1_change_rate：{stability.get('l1_change_rate')}",
        "",
        "## Discriminability Audit",
        "",
        f"- average_l1_l2_gap：{discriminability.get('average_l1_l2_gap')}",
        f"- average_top1_top5_gap：{discriminability.get('average_top1_top5_gap')}",
        f"- score_cluster_flattening_rate：{discriminability.get('score_cluster_flattening_rate')}",
    ]
    return "\n".join(lines)


def write_final_audit_report(
    audit_id: str,
    payload: dict[str, Any],
    markdown: str,
    report_dir: Path = AUDIT_REPORT_DIR,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{audit_id}.json"
    md_path = report_dir / f"{audit_id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path
