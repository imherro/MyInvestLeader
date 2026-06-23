from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT_DIR / "research" / "leaders"
STOCK_REPORT_DIR = ROOT_DIR / "research" / "stocks"
AUDIT_REPORT_DIR = ROOT_DIR / "research" / "audits"
ENV_PATH = ROOT_DIR / ".env"

DEFAULT_THEME_API_URL = "https://theme.okbbc.com/api/latest"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 MyInvestLeader/0.1",
    "Accept": "application/json,text/plain,*/*",
}


@dataclass(frozen=True)
class RuntimeConfig:
    host: str = os.getenv("LEADER_HOST", "127.0.0.1")
    port: int = int(os.getenv("LEADER_PORT", "8014"))
    theme_api_url: str = os.getenv("THEME_API_URL", DEFAULT_THEME_API_URL)


def load_local_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_tushare_token() -> str | None:
    load_local_env()
    for key in ("TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN", "tushare_token"):
        value = os.getenv(key)
        if value:
            return value
    return None
