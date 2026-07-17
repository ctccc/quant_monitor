"""SQLite 存储层。单文件 data/quant.db，零运维。

线程约定：SQLite 连接按需创建、用完即关（check_same_thread 问题由此规避），
写入频率低（盘后归档为主），无需连接池。
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import List, Optional

from quant_monitor.config import DATA_DIR
from quant_monitor.datasource.base import (
    DtPoolItem, MarketMood, SectorFlow, ZbPoolItem, ZtPoolItem,
)

DB_PATH = DATA_DIR / "quant.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS zt_pool (
    date        TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT,
    price       REAL,
    pct         REAL,
    first_seal  TEXT,
    last_seal   TEXT,
    seal_fund   REAL,
    break_times INTEGER,
    boards      INTEGER,
    industry    TEXT,
    fetched_at  TEXT,
    PRIMARY KEY (date, code)
);
CREATE TABLE IF NOT EXISTS sector_flow (
    date       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    code       TEXT NOT NULL,
    name       TEXT,
    pct        REAL,
    main_net   REAL,
    main_pct   REAL,
    fetched_at TEXT,
    PRIMARY KEY (date, kind, code)
);
CREATE TABLE IF NOT EXISTS trade_calendar (
    date TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS zb_pool (
    date        TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT,
    price       REAL,
    pct         REAL,
    first_seal  TEXT,
    break_times INTEGER,
    industry    TEXT,
    fetched_at  TEXT,
    PRIMARY KEY (date, code)
);
CREATE TABLE IF NOT EXISTS dt_pool (
    date       TEXT NOT NULL,
    code       TEXT NOT NULL,
    name       TEXT,
    price      REAL,
    pct        REAL,
    seal_fund  REAL,
    days       INTEGER,
    industry   TEXT,
    fetched_at TEXT,
    PRIMARY KEY (date, code)
);
CREATE TABLE IF NOT EXISTS market_mood (
    date        TEXT PRIMARY KEY,
    up_count    INTEGER,
    down_count  INTEGER,
    flat_count  INTEGER,
    amount      REAL,
    zt_count    INTEGER,
    dt_count    INTEGER,
    zb_count    INTEGER,
    blast_rate  REAL,
    max_boards  INTEGER,
    fetched_at  TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def save_zt_pool(items: List[ZtPoolItem]) -> int:
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO zt_pool VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(i.date, i.code, i.name, i.price, i.pct, i.first_seal, i.last_seal,
              i.seal_fund, i.break_times, i.boards, i.industry, now) for i in items],
        )
    return len(items)


def save_sector_flow(items: List[SectorFlow]) -> int:
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO sector_flow VALUES (?,?,?,?,?,?,?,?)",
            [(i.date, i.kind, i.code, i.name, i.pct, i.main_net, i.main_pct, now)
             for i in items],
        )
    return len(items)


def save_zb_pool(items: List[ZbPoolItem]) -> int:
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO zb_pool VALUES (?,?,?,?,?,?,?,?,?)",
            [(i.date, i.code, i.name, i.price, i.pct, i.first_seal,
              i.break_times, i.industry, now) for i in items],
        )
    return len(items)


def save_dt_pool(items: List[DtPoolItem]) -> int:
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO dt_pool VALUES (?,?,?,?,?,?,?,?,?)",
            [(i.date, i.code, i.name, i.price, i.pct, i.seal_fund,
              i.days, i.industry, now) for i in items],
        )
    return len(items)


def save_market_mood(m: MarketMood) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO market_mood VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (m.date, m.up_count, m.down_count, m.flat_count, m.amount,
             m.zt_count, m.dt_count, m.zb_count, m.blast_rate, m.max_boards, now),
        )


def query_mood(days: int = 15) -> List[dict]:
    """近 N 个有记录的交易日情绪指标,按日期升序返回。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM market_mood ORDER BY date DESC LIMIT ?) "
            "ORDER BY date ASC",
            (days,),
        ).fetchall()
    return [dict(r) for r in rows]


def query_sector_trend(kind: str, days: int = 5) -> List[dict]:
    """近 N 个有记录交易日的板块主力净流入累计,按累计值降序。"""
    with _connect() as conn:
        dates = [r["date"] for r in conn.execute(
            "SELECT DISTINCT date FROM sector_flow WHERE kind=? "
            "ORDER BY date DESC LIMIT ?", (kind, days),
        ).fetchall()]
        if not dates:
            return []
        marks = ",".join("?" for _ in dates)
        rows = conn.execute(
            "SELECT code, name, SUM(main_net) AS total_net, COUNT(*) AS days "
            "FROM sector_flow WHERE kind=? AND date IN ({}) "
            "GROUP BY code".format(marks),
            [kind] + dates,
        ).fetchall()
    return [dict(r) for r in rows]


def save_trade_dates(dates: List[str]) -> None:
    with _connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO trade_calendar VALUES (?)",
            [(d,) for d in dates],
        )


def get_trade_dates() -> set:
    with _connect() as conn:
        rows = conn.execute("SELECT date FROM trade_calendar").fetchall()
    return {r["date"] for r in rows}


def set_meta(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))


def get_meta(key: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def latest_zt_date() -> Optional[str]:
    with _connect() as conn:
        row = conn.execute("SELECT MAX(date) AS d FROM zt_pool").fetchone()
    return row["d"] if row and row["d"] else None


def latest_flow_date() -> Optional[str]:
    with _connect() as conn:
        row = conn.execute("SELECT MAX(date) AS d FROM sector_flow").fetchone()
    return row["d"] if row and row["d"] else None


def query_zt_pool(date: str) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM zt_pool WHERE date=? ORDER BY boards DESC, first_seal ASC",
            (date,),
        ).fetchall()
    return [dict(r) for r in rows]


def query_sector_flow(date: str, kind: str, limit: int = 30) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sector_flow WHERE date=? AND kind=? "
            "ORDER BY main_net DESC LIMIT ?",
            (date, kind, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with _connect() as conn:
        zt_days = conn.execute("SELECT COUNT(DISTINCT date) AS c FROM zt_pool").fetchone()["c"]
        zt_rows = conn.execute("SELECT COUNT(*) AS c FROM zt_pool").fetchone()["c"]
        flow_rows = conn.execute("SELECT COUNT(*) AS c FROM sector_flow").fetchone()["c"]
        cal_rows = conn.execute("SELECT COUNT(*) AS c FROM trade_calendar").fetchone()["c"]
    return {
        "zt_days": zt_days,
        "zt_rows": zt_rows,
        "flow_rows": flow_rows,
        "calendar_rows": cal_rows,
        "last_archive": get_meta("last_archive"),
    }
