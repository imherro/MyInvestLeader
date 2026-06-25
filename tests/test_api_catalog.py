from __future__ import annotations

import asyncio

import httpx

from leader_app import main
from leader_app.service import build_api_catalog


async def _get_api_catalog() -> httpx.Response:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/api")


def test_api_catalog_payload_describes_public_endpoints() -> None:
    catalog = build_api_catalog(base_url="http://127.0.0.1:8014")
    groups = catalog["groups"]
    endpoints = [endpoint for group in groups for endpoint in group["endpoints"]]
    paths = {endpoint["path"] for endpoint in endpoints}

    assert catalog["system"]["name"] == "MyInvestLeader"
    assert catalog["base_url"] == "http://127.0.0.1:8014"
    assert catalog["docs"]["swagger"] == "/docs"
    assert catalog["docs"]["redoc"] == "/redoc"
    assert catalog["docs"]["openapi"] == "/openapi.json"
    assert catalog["total_endpoints"] == len(endpoints)
    assert {group["id"] for group in groups} == {
        "docs",
        "current_data",
        "analysis_results",
        "history_data",
        "system_status",
    }
    assert "/api" in paths
    assert "/api/index" in paths
    assert "/api/stocks/deep/latest" in paths
    assert "/api/stocks/deep/recommendations/history" in paths
    assert "/health" in paths
    assert all(endpoint["method"] == "GET" for endpoint in endpoints)
    assert all(endpoint["read_only"] is True for endpoint in endpoints)
    assert all("purpose" in endpoint and "params" in endpoint and "returns" in endpoint for endpoint in endpoints)
    assert catalog["safety"]["no_recompute"] is True
    assert catalog["safety"]["no_trade_order"] is True
    assert any(item["path"] == "/api/index" for item in catalog["recommended_entrypoints"])


def test_api_catalog_route_is_static_and_read_only(monkeypatch) -> None:
    def fail_latest_report() -> None:
        raise AssertionError("/api must not read latest research")

    monkeypatch.setattr(main, "latest_report", fail_latest_report)

    response = asyncio.run(_get_api_catalog())
    payload = response.json()

    assert response.status_code == 200
    assert payload["base_url"] == "http://testserver"
    assert payload["safety"]["no_write"] is True
    assert payload["total_endpoints"] >= 10
