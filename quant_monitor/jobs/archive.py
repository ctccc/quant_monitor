"""盘后归档任务：抓取当日涨停池 + 板块资金流,落库 SQLite。

既可由调度器在交易日盘后自动触发,也可通过看板按钮/命令行手动触发。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from quant_monitor.datasource import calendar, eastmoney
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

    try:
        n = db.save_zt_pool(eastmoney.fetch_zt_pool(date))
        result["steps"]["zt_pool"] = n
    except Exception as e:  # noqa: BLE001
        result["ok"] = False
        result["errors"].append("涨停池: {!r}".format(e))

    for kind in ("industry", "concept"):
        try:
            n = db.save_sector_flow(eastmoney.fetch_sector_flow(kind, date))
            result["steps"]["sector_" + kind] = n
        except Exception as e:  # noqa: BLE001
            result["ok"] = False
            result["errors"].append("板块({}): {!r}".format(kind, e))

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
