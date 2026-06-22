from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leader_app.config import DEFAULT_THEME_API_URL
from leader_app.research import build_report, write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MyInvestLeader research report.")
    parser.add_argument("--theme-url", default=DEFAULT_THEME_API_URL, help="Mainline latest API URL.")
    parser.add_argument("--write", action="store_true", help="Write JSON and Markdown under research/leaders.")
    args = parser.parse_args()

    report_id, payload, markdown = build_report(theme_url=args.theme_url)
    if args.write:
        json_path, md_path = write_report(report_id, payload, markdown)
        print(json_path)
        print(md_path)
        return
    print(
        json.dumps(
            {
                "report_id": report_id,
                "basis_date": payload.get("basis_date"),
                "theme_report_id": payload.get("upstream", {}).get("theme_report_id"),
                "top": [
                    {
                        "theme": row.get("theme"),
                        "leader_score": row.get("leader_score"),
                        "leader_grade": row.get("leader_grade"),
                    }
                    for row in (payload.get("themes") or [])[:3]
                ],
                "data_gaps": payload.get("data_gaps") or [],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
