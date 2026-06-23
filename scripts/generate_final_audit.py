from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leader_app.final_audit import build_final_audit_report, write_final_audit_report
from leader_app.service import latest_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate final calibration audit from the latest leader report.")
    parser.add_argument("--write", action="store_true", help="Write JSON and Markdown under research/audits.")
    args = parser.parse_args()

    _report_id, leader_payload, _markdown = latest_report()
    audit_id, payload, markdown = build_final_audit_report(leader_payload)
    if args.write:
        json_path, md_path = write_final_audit_report(audit_id, payload, markdown)
        print(json_path)
        print(md_path)
        return
    print(
        json.dumps(
            {
                "audit_id": audit_id,
                "leader_report_id": payload.get("leader_report_id"),
                "basis_date": payload.get("basis_date"),
                "FINAL_SYSTEM_AUDIT_REPORT": payload.get("FINAL_SYSTEM_AUDIT_REPORT"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
