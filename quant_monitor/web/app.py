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


class TradePayload(BaseModel):
    date: str
    code: str
    side: str          # buy | sell
    price: float
    qty: int
    note: str = ""


def _positions_with_quotes() -> list:
    """持仓聚合 + 腾讯快照估值。行情失败时仍返回持仓,价格字段为 None。"""
    from quant_monitor.datasource import tencent

    pos = db.positions()
    quotes = {}
    if pos:
        try:
            quotes = tencent.fetch_quotes([p["code"] for p in pos])
        except Exception:  # noqa: BLE001
            quotes = {}
    for p in pos:
        q = quotes.get(p["code"])
        if q:
            p["name"] = p["name"] or q["name"]
            p["price"] = q["price"]
            p["pct"] = q["pct"]
            p["pnl"] = round((q["price"] - p["avg_cost"]) * p["qty"], 2)
            p["pnl_pct"] = round((q["price"] / p["avg_cost"] - 1) * 100, 2) \
                if p["avg_cost"] else None
        else:
            p["price"] = p["pct"] = p["pnl"] = p["pnl_pct"] = None
    return pos


@app.get("/api/positions")
def positions() -> dict:
    return {"items": _positions_with_quotes()}


@app.get("/api/trades")
def trades(limit: int = 30) -> dict:
    return {"items": db.query_trades(min(limit, 200))}


@app.post("/api/trade")
def add_trade(payload: TradePayload) -> JSONResponse:
    if payload.side not in ("buy", "sell"):
        return JSONResponse({"error": "side 应为 buy/sell"}, status_code=400)
    if not _DATE_RE.match(payload.date):
        return JSONResponse({"error": "日期格式应为 YYYY-MM-DD"}, status_code=400)
    code = payload.code.strip().zfill(6)
    if not code.isdigit() or len(code) != 6:
        return JSONResponse({"error": "代码应为6位数字"}, status_code=400)
    if payload.price <= 0 or payload.qty <= 0:
        return JSONResponse({"error": "价格与数量需为正数"}, status_code=400)
    name = ""
    try:
        from quant_monitor.datasource import tencent
        name = tencent.fetch_quotes([code]).get(code, {}).get("name", "")
    except Exception:  # noqa: BLE001
        pass
    tid = db.add_trade(payload.date, code, name, payload.side,
                       payload.price, payload.qty, payload.note)
    return JSONResponse({"id": tid, "name": name, "saved": True})


@app.delete("/api/trade/{tid}")
def remove_trade(tid: int) -> JSONResponse:
    ok = db.delete_trade(tid)
    return JSONResponse({"deleted": ok}, status_code=200 if ok else 404)


@app.post("/api/ai/review")
def ai_review(date: Optional[str] = None) -> JSONResponse:
    """生成 AI 复盘摘要(同步调用 LLM,约需十几秒)。"""
    from quant_monitor.llm.client import LLMDisabled, llm_enabled
    from quant_monitor.llm.review import generate_review

    if not llm_enabled():
        return JSONResponse(
            {"error": "AI 功能未启用:在 config.yaml 的 llm 段填入 api_key "
                      "并设 enabled: true,然后重启应用"},
            status_code=501)
    date = date or db.latest_zt_date()
    if not date:
        return JSONResponse({"error": "尚无归档数据,请先归档"}, status_code=400)
    pos = [{"名称": p["name"] or p["code"], "当日涨跌幅": p["pct"],
            "浮动盈亏比": p["pnl_pct"]} for p in _positions_with_quotes()]
    try:
        content = generate_review(date, pos or None)
    except LLMDisabled as e:
        return JSONResponse({"error": str(e)}, status_code=501)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": "LLM 调用失败: {!r}".format(e)},
                            status_code=502)
    return JSONResponse({"date": date, "content": content})


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


@app.post("/api/ai/trade-review")
def ai_trade_review() -> JSONResponse:
    """AI 交易复盘:逐笔诊断 + 期间市场环境归因(同步调用,约需半分钟)。"""
    from quant_monitor.llm.client import LLMDisabled, llm_enabled
    from quant_monitor.llm.trade_review import generate_trade_review

    if not llm_enabled():
        return JSONResponse(
            {"error": "AI 功能未启用:在 config.yaml 的 llm 段填入 api_key "
                      "并设 enabled: true,然后重启应用"},
            status_code=501)
    try:
        content = generate_trade_review()
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except LLMDisabled as e:
        return JSONResponse({"error": str(e)}, status_code=501)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": "生成失败: {!r}".format(e)}, status_code=502)
    return JSONResponse({"content": content})


@app.post("/api/jobs/archive")
def archive_now() -> JSONResponse:
    """手动触发一次盘后归档(同步执行,含全市场扫描约需半分钟)。"""
    result = run_archive()
    return JSONResponse(result, status_code=200 if result["ok"] else 502)
