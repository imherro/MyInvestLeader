from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from leader_app.config import RuntimeConfig


def main() -> None:
    config = RuntimeConfig()
    parser = argparse.ArgumentParser(description="Run MyInvestLeader web app.")
    parser.add_argument("--host", default=config.host)
    parser.add_argument("--port", type=int, default=config.port)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("leader_app.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
