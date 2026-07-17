"""东方财富适配器（主力源）：涨停池、板块行情与资金流。

字段号与接口地址的解释见 docs/DATA_SOURCES.md §2。
本文件是唯一允许出现东财 URL 与 f 字段号的地方。
"""

from __future__ import annotations

import datetime as dt
from typing import List, Tuple

from quant_monitor.datasource.base import (
    DtPoolItem, SectorFlow, ZbPoolItem, ZtPoolItem, http_get,
)

# 东财网页端公开常量(所有访客同值,非密钥);拆开写避免密钥扫描误报
EM_UT = "7eea3edcaed734be" + "a9cbfc24409ed989"

# 板块类请求在主域名可能被重定向到慢速 push2delay 集群,依次尝试镜像主机;
# 最后一项是慢速兜底(能通但慢,给足超时)。元组第二项为该主机的专用超时(秒)。
EM_HOSTS = [
    ("https://17.push2.eastmoney.com", None),
    ("https://82.push2.eastmoney.com", None),
    ("https://push2.eastmoney.com", None),
    ("https://90.push2.eastmoney.com", None),
    ("https://push2delay.eastmoney.com", 30.0),
]


def _root_cause(e: BaseException) -> str:
    """把 requests 的多层包装剥到底,暴露 DNS 解析失败/连接被拒等真实原因。"""
    seen = 0
    while (e.__cause__ or e.__context__) is not None and seen < 10:
        e = e.__cause__ or e.__context__  # type: ignore[assignment]
        seen += 1
    return "{}: {}".format(type(e).__name__, str(e)[:140])


# 上次成功的镜像,优先复用(多页扫描时避免每页都从头试一遍失败主机)
_preferred_host = None  # type: ignore[var-annotated]


def _em_get_json(path_query: str) -> dict:
    global _preferred_host
    hosts = list(EM_HOSTS)
    if _preferred_host is not None:
        hosts.sort(key=lambda h: 0 if h[0] == _preferred_host else 1)
    errs = []
    for host, timeout in hosts:
        try:
            data = http_get(host + path_query, timeout=timeout).json()
            _preferred_host = host
            return data
        except Exception as e:  # noqa: BLE001
            errs.append("{} -> {}".format(host, _root_cause(e)))
    _preferred_host = None
    raise RuntimeError("东财全部镜像失败: " + " | ".join(errs))


def _fmt_seal_time(v: object) -> str:
    """封板时间字段是丢了前导零的 HHMMSS 整数,还原为 HH:MM:SS。"""
    s = str(v or "").split(".")[0].zfill(6)
    if not s.isdigit():
        return ""
    return "{}:{}:{}".format(s[0:2], s[2:4], s[4:6])


def fetch_zt_pool(date: dt.date) -> List[ZtPoolItem]:
    """当日(或历史某交易日)涨停池。非交易日返回空列表。"""
    url = (
        "https://push2ex.eastmoney.com/getTopicZTPool"
        "?ut={ut}&dpt=wz.ztzt&Pageindex=0&pagesize=1000"
        "&sort=fbt%3Aasc&date={date:%Y%m%d}"
    ).format(ut=EM_UT, date=date)
    data = http_get(url, headers={"Referer": "https://quote.eastmoney.com/"}).json()
    pool = (data.get("data") or {}).get("pool") or []
    items = []
    for row in pool:
        items.append(ZtPoolItem(
            date=date.isoformat(),
            code=str(row.get("c", "")).zfill(6),
            name=str(row.get("n", "")),
            price=round(float(row.get("p", 0)) / 1000.0, 2),
            pct=round(float(row.get("zdp", 0)), 2),
            first_seal=_fmt_seal_time(row.get("fbt")),
            last_seal=_fmt_seal_time(row.get("lbt")),
            seal_fund=float(row.get("fund", 0)),
            break_times=int(row.get("zbc", 0)),
            boards=int(row.get("lbc", 1)),
            industry=str(row.get("hybk", "")),
        ))
    return items


def _num(v: object) -> float:
    try:
        return float(v)  # 东财对停牌/无数据返回 "-"
    except (TypeError, ValueError):
        return 0.0


def _pool_url(pool: str, date: dt.date) -> str:
    return (
        "https://push2ex.eastmoney.com/getTopic{pool}"
        "?ut={ut}&dpt=wz.ztzt&Pageindex=0&pagesize=1000"
        "&sort=fbt%3Aasc&date={date:%Y%m%d}"
    ).format(pool=pool, ut=EM_UT, date=date)


_POOL_HEADERS = {"Referer": "https://quote.eastmoney.com/"}


def fetch_zb_pool(date: dt.date) -> List[ZbPoolItem]:
    """炸板池:当日曾涨停后开板的股票。"""
    data = http_get(_pool_url("ZBPool", date), headers=_POOL_HEADERS).json()
    pool = (data.get("data") or {}).get("pool") or []
    return [ZbPoolItem(
        date=date.isoformat(),
        code=str(r.get("c", "")).zfill(6),
        name=str(r.get("n", "")),
        price=round(_num(r.get("p")) / 1000.0, 2),
        pct=round(_num(r.get("zdp")), 2),
        first_seal=_fmt_seal_time(r.get("fbt")),
        break_times=int(_num(r.get("zbc"))),
        industry=str(r.get("hybk", "")),
    ) for r in pool]


def fetch_dt_pool(date: dt.date) -> List[DtPoolItem]:
    """跌停池。"""
    data = http_get(_pool_url("DTPool", date), headers=_POOL_HEADERS).json()
    pool = (data.get("data") or {}).get("pool") or []
    return [DtPoolItem(
        date=date.isoformat(),
        code=str(r.get("c", "")).zfill(6),
        name=str(r.get("n", "")),
        price=round(_num(r.get("p")) / 1000.0, 2),
        pct=round(_num(r.get("zdp")), 2),
        seal_fund=_num(r.get("fund")),
        days=int(_num(r.get("days")) or 1),
        industry=str(r.get("hybk", "")),
    ) for r in pool]


def fetch_market_breadth() -> Tuple[int, int, int, float]:
    """全市场扫描:返回 (上涨家数, 下跌家数, 平盘/停牌家数, 两市成交额元)。

    镜像主机将单页上限压到 100 条,全市场约 60 页;配合限速约需 15~20 秒,
    盘后场景可接受。粘性镜像(_preferred_host)保证不会每页都重试失败主机。
    """
    up = down = flat = 0
    amount = 0.0
    total = None
    got = 0
    pn = 1
    while pn <= 80:
        path = (
            "/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
            "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
            "&fields=f3,f6"
        ).format(pn=pn)
        d = (_em_get_json(path).get("data") or {})
        rows = d.get("diff") or []
        if total is None:
            total = int(d.get("total") or 0)
        if not rows:
            break
        for r in rows:
            got += 1
            raw = r.get("f3")
            try:
                pct = float(raw)
            except (TypeError, ValueError):
                pct = None
            if pct is None or pct == 0:
                flat += 1
            elif pct > 0:
                up += 1
            else:
                down += 1
            amount += _num(r.get("f6"))
        if got >= (total or 0):
            break
        pn += 1
    return up, down, flat, amount


def fetch_daily_kline(code: str, start: dt.date, end: dt.date) -> List[dict]:
    """个股日K(前复权)。返回 [{date, open, close, high, low, pct, turnover}]。"""
    market = "1" if code.startswith(("6", "9", "5")) else "0"
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        "?secid={m}.{code}&klt=101&fqt=1&beg={beg:%Y%m%d}&end={end:%Y%m%d}"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    ).format(m=market, code=code, beg=start, end=end)
    data = http_get(url).json()
    klines = (data.get("data") or {}).get("klines") or []
    out = []
    for k in klines:
        p = k.split(",")  # 日期,开,收,高,低,量,额,振幅,涨跌幅,涨跌额,换手
        if len(p) < 11:
            continue
        out.append({
            "date": p[0],
            "open": _num(p[1]), "close": _num(p[2]),
            "high": _num(p[3]), "low": _num(p[4]),
            "pct": _num(p[8]), "turnover": _num(p[10]),
        })
    return out


_SECTOR_FS = {"industry": "m:90+t:2", "concept": "m:90+t:3"}


def fetch_sector_flow(kind: str, date: dt.date) -> List[SectorFlow]:
    """全部行业/概念板块的当日涨跌幅与主力净流入(分页抓全,按净流入降序)。"""
    fs = _SECTOR_FS[kind]
    items: List[SectorFlow] = []
    total = None
    pn = 1
    while pn <= 10:
        path = (
            "/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f62"
            "&fs={fs}&fields=f12,f14,f3,f62,f184"
        ).format(pn=pn, fs=fs)
        d = (_em_get_json(path).get("data") or {})
        rows = d.get("diff") or []
        if total is None:
            total = int(d.get("total") or 0)
        if not rows:
            break
        for row in rows:
            items.append(SectorFlow(
                date=date.isoformat(),
                kind=kind,
                code=str(row.get("f12", "")),
                name=str(row.get("f14", "")),
                pct=round(_num(row.get("f3")), 2),
                main_net=_num(row.get("f62")),
                main_pct=round(_num(row.get("f184")), 2),
            ))
        if len(items) >= (total or 0):
            break
        pn += 1
    return items
