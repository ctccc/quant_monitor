"""腾讯行情适配器（快照备用源）：按代码批量取实时/收盘快照。

用于持仓估值等小批量场景,不承担全市场轮询。
"""

from __future__ import annotations

from typing import Dict, List

from quant_monitor.datasource.base import http_get


def _prefix(code: str) -> str:
    """A股代码 → 交易所前缀。"""
    if code.startswith(("60", "68", "90")):
        return "sh"
    if code.startswith(("00", "30", "20")):
        return "sz"
    return "bj"  # 8/4/92 开头为北交所


def fetch_quotes(codes: List[str]) -> Dict[str, dict]:
    """返回 {代码: {name, price, pct, prev_close}}。单次最多约 60 只。

    腾讯接口返回 GBK 编码、~ 分隔:v[1]=名称 v[3]=现价 v[4]=昨收 v[32]=涨跌幅%。
    """
    codes = [c for c in codes if c][:60]
    if not codes:
        return {}
    q = ",".join(_prefix(c) + c for c in codes)
    resp = http_get("https://qt.gtimg.cn/q=" + q)
    text = resp.content.decode("gbk", errors="replace")
    out: Dict[str, dict] = {}
    for line in text.strip().split(";"):
        line = line.strip()
        if "=" not in line or '"' not in line:
            continue
        v = line.split('"')[1].split("~")
        if len(v) < 33:
            continue
        code = v[2]

        def _f(x: str) -> float:
            try:
                return float(x)
            except ValueError:
                return 0.0

        out[code] = {
            "name": v[1],
            "price": _f(v[3]),
            "prev_close": _f(v[4]),
            "pct": _f(v[32]),
        }
    return out
