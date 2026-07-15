"""命令行入口。

    python3 -m quant_monitor           # 启动看板(默认 http://127.0.0.1:8000)
    python3 -m quant_monitor archive   # 不开看板,只执行一次盘后归档
"""

from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(prog="quant_monitor", description=__doc__)
    parser.add_argument(
        "command", nargs="?", default="serve", choices=["serve", "archive"],
        help="serve=启动看板(默认); archive=执行一次归档后退出",
    )
    args = parser.parse_args()

    if args.command == "archive":
        from quant_monitor.jobs.archive import run_archive
        from quant_monitor.store import db

        db.init_db()
        result = run_archive()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(0 if result["ok"] else 1)

    import uvicorn

    from quant_monitor.config import CONFIG

    uvicorn.run(
        "quant_monitor.web.app:app",
        host=CONFIG["web"]["host"],
        port=CONFIG["web"]["port"],
    )


if __name__ == "__main__":
    main()
