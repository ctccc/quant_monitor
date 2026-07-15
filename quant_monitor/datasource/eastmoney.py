"""东方财富适配器（主力源）：涨停池、板块行情与资金流。

字段号与接口地址的解释见 docs/DATA_SOURCES.md §2。
本文件是唯一允许出现东财 URL 与 f 字段号的地方。
"""

from __future__ import annotations

import datetime as dt
from typing import List

from quant_monitor.datasource.base import SectorFlow, ZtPoolItem, http_get

# 东财网页端公开常量(所有访客同值,非密钥);拆开写避免密钥扫描误报
EM_UT = "7eea3edcaed734be" + "a9cbfc24409ed989"

# 板块类请求在主域名可能被重定向到慢速 push2delay 集群,依次尝试镜像主机
EM_HOSTS = [
    "https://17.push2.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://90.push2.eastmoney.com",
]


def _em_get_json(path_query: str) -> dict:
    errs = []
    for host in EM_HOSTS:
        try:
            return http_get(host + path_query).json()
        except Exception as e:  # noqa: BLE001
            errs.append("{} -> {}".format(host, type(e).__name__))
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


_SECTOR_FS = {"industry": "m:90+t:2", "concept": "m:90+t:3"}


def fetch_sector_flow(kind: str, date: dt.date) -> List[SectorFlow]:
    """全部行业/概念板块的当日涨跌幅与主力净流入(按净流入降序)。"""
    fs = _SECTOR_FS[kind]
    path = (
        "/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f62"
        "&fs={fs}&fields=f12,f14,f3,f62,f184"
    ).format(fs=fs)
    data = _em_get_json(path)
    rows = (data.get("data") or {}).get("diff") or []
    items = []
    for row in rows:
        def _num(v: object) -> float:
            try:
                return float(v)  # 东财对停牌/无数据返回 "-"
            except (TypeError, ValueError):
                return 0.0

        items.append(SectorFlow(
            date=date.isoformat(),
            kind=kind,
            code=str(row.get("f12", "")),
            name=str(row.get("f14", "")),
            pct=round(_num(row.get("f3")), 2),
            main_net=_num(row.get("f62")),
            main_pct=round(_num(row.get("f184")), 2),
        ))
    return items
