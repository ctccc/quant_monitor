"""交易日历：优先用 akshare 拉取并缓存到 SQLite，离线/失败时退化为工作日判断。"""

from __future__ import annotations

import datetime as dt
from typing import List, Optional


def fetch_trade_dates() -> Optional[List[str]]:
    """从 akshare 拉取全部交易日(ISO 字符串)。akshare 缺失或失败返回 None。"""
    try:
        import akshare as ak  # noqa: PLC0415
        df = ak.tool_trade_date_hist_sina()
        return [str(d) for d in df["trade_date"].astype(str).tolist()]
    except Exception:  # noqa: BLE001
        return None


def is_trade_day(date: dt.date, cached_dates: Optional[set] = None) -> bool:
    """cached_dates 为空(日历不可用)时退化为周一~周五判断。"""
    if cached_dates:
        return date.isoformat() in cached_dates
    return date.weekday() < 5


def latest_trade_day(today: dt.date, cached_dates: Optional[set] = None) -> dt.date:
    """今天或之前最近的一个交易日。"""
    d = today
    for _ in range(30):
        if is_trade_day(d, cached_dates):
            return d
        d -= dt.timedelta(days=1)
    return today
