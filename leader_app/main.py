from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import ROOT_DIR
from .service import (
    build_index_payload,
    latest_report,
    latest_stock_report,
    list_recommendation_history,
    list_reports,
    list_stock_reports,
    load_markdown,
    load_report,
    load_stock_markdown,
    load_stock_report,
)


app = FastAPI(
    title="MyInvestLeader",
    version="0.1.0",
    description="Read-only A-share mainline leader research and shadow-account input API.",
)

app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    response = templates.TemplateResponse(request, "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health() -> dict[str, Any]:
    reports = list_reports()
    stock_reports = list_stock_reports()
    return {
        "ok": True,
        "read_only": True,
        "report_count": len(reports),
        "latest_report_id": reports[0]["report_id"] if reports else None,
        "stock_deep_report_count": len(stock_reports),
        "latest_stock_deep_report_id": stock_reports[0]["report_id"] if stock_reports else None,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/index")
def api_index() -> dict[str, Any]:
    report_id, payload, markdown = latest_report()
    return build_index_payload(report_id, payload, markdown)


@app.get("/api/latest")
def api_latest() -> dict[str, Any]:
    report_id, payload, _markdown = latest_report()
    return {"report_id": report_id, "result": payload}


@app.get("/api/shadow/latest")
def api_shadow_latest() -> dict[str, Any]:
    _report_id, payload, _markdown = latest_report()
    return payload.get("shadow_contract") or {}


@app.get("/api/reports")
def api_reports() -> dict[str, Any]:
    return {"reports": list_reports()}


@app.get("/api/stocks/deep/latest")
def api_stock_deep_latest() -> dict[str, Any]:
    latest = latest_stock_report()
    if latest is None:
        return {"report_id": None, "result": None}
    report_id, payload, _markdown = latest
    return {"report_id": report_id, "result": payload}


@app.get("/api/stocks/deep/shadow/latest")
def api_stock_deep_shadow_latest() -> dict[str, Any]:
    latest = latest_stock_report()
    if latest is None:
        return {}
    _report_id, payload, _markdown = latest
    return payload.get("shadow_contract") or {}


@app.get("/api/stocks/deep/reports")
def api_stock_deep_reports() -> dict[str, Any]:
    return {"reports": list_stock_reports()}


@app.get("/api/stocks/deep/recommendations/history")
def api_stock_deep_recommendation_history() -> dict[str, Any]:
    return {"records": list_recommendation_history()}


@app.get("/api/stocks/deep/reports/{report_id}")
def api_stock_deep_report(report_id: str) -> dict[str, Any]:
    return {"report_id": report_id, "result": load_stock_report(report_id)}


@app.get("/api/stocks/deep/reports/{report_id}/markdown")
def api_stock_deep_report_markdown(report_id: str) -> PlainTextResponse:
    return PlainTextResponse(load_stock_markdown(report_id), media_type="text/markdown; charset=utf-8")


@app.get("/api/reports/{report_id}")
def api_report(report_id: str) -> dict[str, Any]:
    return {"report_id": report_id, "result": load_report(report_id)}


@app.get("/api/reports/{report_id}/markdown")
def api_report_markdown(report_id: str) -> PlainTextResponse:
    return PlainTextResponse(load_markdown(report_id), media_type="text/markdown; charset=utf-8")
