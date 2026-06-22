from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

import httpx

from .config import HTTP_HEADERS


ETF_CODE_RE = re.compile(r"\b(?P<code>\d{6}\.(?:SH|SZ|BJ))\b\s*(?P<name>[^、,，;；]*)")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def stable_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_json(url: str) -> dict[str, Any]:
    with httpx.Client(headers=HTTP_HEADERS, timeout=30.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def parse_etf_candidates(text: str | None) -> list[dict[str, str]]:
    if not text:
        return []
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for match in ETF_CODE_RE.finditer(text):
        code = match.group("code")
        if code in seen:
            continue
        seen.add(code)
        name = match.group("name").strip(" -_/，,、;；")
        result.append({"code": code, "name": name or code})
    return result


def latest_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    return result if isinstance(result, dict) else payload
