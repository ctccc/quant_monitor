"""数据接入层公共设施：直连会话、全局限速、统一数据模型。

设计原则（详见 docs/ARCHITECTURE.md §3）：
- 业务代码只依赖本文件定义的数据模型，不接触任何具体接口 URL/字段号。
- 国内行情站点一律直连，绕开 VPN/加速器注册的系统代理（体检脚本已验证
  系统代理是"接口忽通忽断"的元凶）。
- 所有出站请求共享一个全局限速器，防止触发反爬。
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import requests

from quant_monitor.config import CONFIG

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# 让本进程内其他库(如 akshare)访问这些站点时也绕开系统代理
_DIRECT_HOSTS = ".eastmoney.com,.gtimg.cn,.sinajs.cn,.sina.com.cn,.10jqka.com.cn"
os.environ["NO_PROXY"] = _DIRECT_HOSTS
os.environ["no_proxy"] = _DIRECT_HOSTS


class RateLimiter:
    """全局限速器：保证全进程对外请求不超过 max_per_sec 次/秒。"""

    def __init__(self, max_per_sec: float):
        self._interval = 1.0 / max(max_per_sec, 0.1)
        self._lock = threading.Lock()
        self._last = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._last = now


_limiter = RateLimiter(CONFIG["datasource"]["max_per_sec"])

_session = requests.Session()
_session.trust_env = False  # 无视环境变量/系统代理,强制直连
_session.headers["User-Agent"] = UA


def http_get(url: str, headers: Optional[dict] = None,
             timeout: Optional[float] = None) -> requests.Response:
    """带全局限速的直连 GET。失败按配置重试。"""
    timeout = timeout or CONFIG["datasource"]["timeout"]
    retries = CONFIG["datasource"]["retries"]
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        _limiter.acquire()
        try:
            resp = _session.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt < retries:
                time.sleep(1.0)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------- 统一数据模型


@dataclass
class ZtPoolItem:
    """涨停池条目（一只当日涨停的股票）。"""

    date: str            # YYYY-MM-DD
    code: str
    name: str
    price: float         # 最新价(元)
    pct: float           # 涨跌幅(%)
    first_seal: str      # 首次封板时间 HH:MM:SS
    last_seal: str       # 最后封板时间 HH:MM:SS
    seal_fund: float     # 封单资金(元)
    break_times: int     # 炸板次数
    boards: int          # 连板数
    industry: str        # 所属行业


@dataclass
class SectorFlow:
    """板块（行业/概念）当日行情与主力资金净流入。"""

    date: str            # YYYY-MM-DD
    kind: str            # industry | concept
    code: str            # 如 BK0475
    name: str
    pct: float           # 板块涨跌幅(%)
    main_net: float      # 主力净流入(元)
    main_pct: float      # 主力净占比(%)
