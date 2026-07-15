"""进程内调度器：随 Web 应用启动,按交易时段自动执行任务。

M0 只有一个任务:交易日盘后归档。后续里程碑在此追加盘前/盘中任务。
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from quant_monitor.config import CONFIG
from quant_monitor.jobs.archive import scheduled_archive

log = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Shanghai")

_scheduler = None  # type: ignore[var-annotated]


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone=TZ)
    sched.add_job(
        scheduled_archive,
        "cron",
        day_of_week="mon-fri",
        hour=CONFIG["archive"]["hour"],
        minute=CONFIG["archive"]["minute"],
        id="post_market_archive",
        misfire_grace_time=3600,
    )
    sched.start()
    _scheduler = sched
    log.info("scheduler started: 盘后归档 %02d:%02d",
             CONFIG["archive"]["hour"], CONFIG["archive"]["minute"])
    return sched


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
