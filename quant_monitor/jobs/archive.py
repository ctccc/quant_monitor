"""盘后归档任务：抓取当日涨停池 + 板块资金流,落库 SQLite。

既可由调度器在交易日盘后自动触发,也可通过看板按钮/命令行手动触发。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from quant_monitor.datasource import calendar, eastmoney
from quant_monitor.datasource.base import MarketMood
from quant_monitor.store import db

log = logging.getLogger(__name__)


def ensure_calendar() -> set:
    """保证 SQLite 里有交易日历;拉取失败时返回已有缓存(可能为空)。"""
    cached = db.get_trade_dates()
    this_year = str(dt.date.today().year)
    if not any(d.startswith(this_year) for d in cached):
        dates = calendar.fetch_trade_dates()
        if dates:
            db.save_trade_dates(dates)
            cached = db.get_trade_dates()
    return cached


def run_archive(target: Optional[dt.date] = None) -> dict:
    """执行一次归档。返回结果摘要 dict(供 API/命令行显示)。"""
    cached = ensure_calendar()
    today = dt.date.today()
    date = target or calendar.latest_trade_day(today, cached)

    result = {"date": date.isoformat(), "ok": True, "steps": {}, "errors": []}

    def _step(name, fn):
        try:
            result["steps"][name] = fn()
            return True
        except Exception as e:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append("{}: {!r}".format(name, e))
            return False

    zt_items = []
    zb_items = []

    def _zt():
        zt_items.extend(eastmoney.fetch_zt_pool(date))
        return db.save_zt_pool(zt_items)

    def _zb():
        zb_items.extend(eastmoney.fetch_zb_pool(date))
        return db.save_zb_pool(zb_items)

    _step("zt_pool", _zt)
    _step("zb_pool", _zb)
    dt_ok = {"n": None}

    def _dt():
        items = eastmoney.fetch_dt_pool(date)
        dt_ok["n"] = len(items)
        return db.save_dt_pool(items)

    _step("dt_pool", _dt)
    for kind in ("industry", "concept"):
        _step("sector_" + kind,
              lambda k=kind: db.save_sector_flow(eastmoney.fetch_sector_flow(k, date)))

    def _mood():
        up, down, flat, amount = eastmoney.fetch_market_breadth()
        zt_n, zb_n = len(zt_items), len(zb_items)
        mood = MarketMood(
            date=date.isoformat(),
            up_count=up, down_count=down, flat_count=flat, amount=amount,
            zt_count=zt_n,
            dt_count=dt_ok["n"] if dt_ok["n"] is not None else 0,
            zb_count=zb_n,
            blast_rate=round(zb_n / (zt_n + zb_n), 4) if (zt_n + zb_n) else 0.0,
            max_boards=max((i.boards for i in zt_items), default=0),
        )
        db.save_market_mood(mood)
        return "涨{} 跌{} 额{:.0f}亿".format(up, down, amount / 1e8)

    _step("market_mood", _mood)

    if result["ok"]:
        db.set_meta("last_archive", dt.datetime.now().isoformat(timespec="seconds"))
    log.info("archive %s: %s", date, result)
    return result


def scheduled_archive() -> None:
    """调度器入口:仅交易日执行。"""
    cached = db.get_trade_dates()
    today = dt.date.today()
    if not calendar.is_trade_day(today, cached):
        log.info("archive skipped: %s 非交易日", today)
        return
    run_archive(today)
