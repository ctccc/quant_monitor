"""FastAPI 应用：极简看板 + JSON API。调度器随应用启动。"""

from __future__ import annotations

import datetime as dt
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from quant_monitor import __version__
from quant_monitor.config import ROOT
from quant_monitor.jobs import scheduler
from quant_monitor.jobs.archive import run_archive
from quant_monitor.store import db

STATIC_DIR = Path(__file__).parent / "static"
NOTES_DIR = ROOT / "notes"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


@app.get("/api/mood")
def mood(days: int = 15) -> dict:
    return {"items": db.query_mood(min(days, 60))}


@app.get("/api/sectortrend")
def sectortrend(kind: str = "industry", days: int = 5) -> dict:
    if kind not in ("industry", "concept"):
        return {"items": []}
    return {"days": days, "items": db.query_sector_trend(kind, days)}


class NotePayload(BaseModel):
    date: str
    content: str


def _note_path(date: str) -> Optional[Path]:
    if not _DATE_RE.match(date):
        return None
    return NOTES_DIR / "{}.md".format(date)


@app.get("/api/note")
def get_note(date: str) -> JSONResponse:
    path = _note_path(date)
    if path is None:
        return JSONResponse({"error": "日期格式应为 YYYY-MM-DD"}, status_code=400)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return JSONResponse({"date": date, "content": content})


@app.post("/api/note")
def save_note(payload: NotePayload) -> JSONResponse:
    path = _note_path(payload.date)
    if path is None:
        return JSONResponse({"error": "日期格式应为 YYYY-MM-DD"}, status_code=400)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.content, encoding="utf-8")
    return JSONResponse({"date": payload.date, "saved": True})


@app.post("/api/jobs/archive")
def archive_now() -> JSONResponse:
    """手动触发一次盘后归档(同步执行,含全市场扫描约需半分钟)。"""
    result = run_archive()
    return JSONResponse(result, status_code=200 if result["ok"] else 502)
