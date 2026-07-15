"""FastAPI 应用：极简看板 + JSON API。调度器随应用启动。"""

from __future__ import annotations

import datetime as dt
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from quant_monitor import __version__
from quant_monitor.jobs import scheduler
from quant_monitor.jobs.archive import run_archive
from quant_monitor.store import db

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db.init_db()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Quant Monitor", version=__version__, lifespan=lifespan)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status() -> dict:
    return {
        "version": __version__,
        "now": dt.datetime.now().isoformat(timespec="seconds"),
        "stats": db.stats(),
    }


@app.get("/api/ztpool")
def ztpool(date: Optional[str] = None) -> dict:
    date = date or db.latest_zt_date()
    if not date:
        return {"date": None, "items": []}
    return {"date": date, "items": db.query_zt_pool(date)}


@app.get("/api/sectorflow")
def sectorflow(kind: str = "industry", date: Optional[str] = None, limit: int = 15) -> dict:
    if kind not in ("industry", "concept"):
        return {"date": None, "kind": kind, "items": []}
    date = date or db.latest_flow_date()
    if not date:
        return {"date": None, "kind": kind, "items": []}
    return {"date": date, "kind": kind, "items": db.query_sector_flow(date, kind, limit)}


@app.post("/api/jobs/archive")
def archive_now() -> JSONResponse:
    """手动触发一次盘后归档(同步执行,网络请求约数秒)。"""
    result = run_archive()
    return JSONResponse(result, status_code=200 if result["ok"] else 502)
