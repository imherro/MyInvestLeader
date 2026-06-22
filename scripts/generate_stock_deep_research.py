from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leader_app.deep_research import build_stock_deep_report, write_stock_deep_report
from leader_app.service import latest_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deep stock research from latest leader report.")
    parser.add_argument("--max-per-theme", type=int, default=3)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    _leader_report_id, leader_payload, _markdown = latest_report()
    report_id, payload, markdown = build_stock_deep_report(leader_payload, max_per_theme=args.max_per_theme)
    if args.write:
        json_path, md_path = write_stock_deep_report(report_id, payload, markdown)
        print(json_path)
        print(md_path)
        return
    print(
        json.dumps(
            {
                "report_id": report_id,
                "leader_report_id": payload.get("leader_report_id"),
                "basis_date": payload.get("basis_date"),
                "summary": payload.get("summary"),
                "top": [
                    {
                        "code": row.get("code"),
                        "name": row.get("name"),
                        "theme": row.get("theme"),
                        "deep_rating": row.get("deep_rating"),
                        "deep_score": row.get("deep_score"),
                    }
                    for row in (payload.get("stocks") or [])[:5]
                ],
                "data_gaps": payload.get("data_gaps") or [],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
