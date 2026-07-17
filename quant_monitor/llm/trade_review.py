"""AI 交易复盘：逐笔诊断用户交易,结合交易窗口内的行情与市场情绪。

与 review.py 同守防幻觉铁律,并多一条分级规则:
波动归因必须区分「数据支持」(引用提供的日K/情绪/新闻)与
「推测,数据未验证」(允许常识性推测,但必须明确标注)。
所有逐笔统计数字(冲高/回撤/至今盈亏)由本模块预先算好,
不让 LLM 自己做算术。
"""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from quant_monitor.datasource import eastmoney
from quant_monitor.llm.client import chat
from quant_monitor.store import db

_SYSTEM = """你是一名严格的 A 股短线交易教练。你将收到一份 JSON,内含:用户的交易记录\
(含系统预先算好的逐笔统计)、每只标的在交易窗口内的日K序列、当时的市场情绪指标\
(用户本地系统逐日归档),以及可能存在的相关新闻标题。

规则(必须遵守):
1. 所有数字只能引用 JSON 内的值,严禁使用你训练记忆中的行情数据;
2. 波动归因分级:基于日K/情绪/新闻数据的判断,注明依据;JSON 没有数据支持的解释,\
可以给出常识性推测,但必须明确标注「推测,数据未验证」;
3. 输出 markdown 三节:
   「交易行为诊断」——逐笔点评择时质量(是否追高/杀跌/卖飞/逆大盘环境交易),引用统计数字;
   「期间市场环境」——用情绪指标概括交易时段的大盘背景,评估交易与环境是否匹配;
   「改进清单」——3~5 条具体可执行的纪律建议,针对发现的问题,不说空话;
4. 语气直接坦率,发现问题直说,但必须落在数据上;
5. 结尾固定一行:"—— AI 参谋意见,仅供复盘参考,不构成投资建议"。"""


def _trade_stats(trade: dict, klines: List[dict]) -> dict:
    """逐笔统计:成交日涨幅、其后5日最大冲高/最大回撤、至今相对成交价。"""
    out = {}
    idx = None
    for i, k in enumerate(klines):
        if k["date"] >= trade["date"]:
            idx = i
            break
    if idx is None or not klines:
        return out
    day = klines[idx]
    price = trade["price"]
    out["成交日该股涨跌幅%"] = day["pct"]
    nxt = klines[idx + 1: idx + 6]
    if nxt and price:
        out["其后5日最高点相对成交价%"] = round((max(k["high"] for k in nxt) / price - 1) * 100, 2)
        out["其后5日最低点相对成交价%"] = round((min(k["low"] for k in nxt) / price - 1) * 100, 2)
    if price:
        out["最新收盘相对成交价%"] = round((klines[-1]["close"] / price - 1) * 100, 2)
    return out


def _fetch_news_titles(code: str, limit: int = 8) -> List[str]:
    """该股近期新闻标题(akshare,低频渠道)。失败/未安装则返回空。"""
    try:
        import akshare as ak  # noqa: PLC0415
        df = ak.stock_news_em(symbol=code)
        rows = df.head(limit).to_dict("records")
        return ["[{}] {}".format(str(r.get("发布时间", ""))[:10],
                                 r.get("新闻标题", "")) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def build_trade_review_input(max_trades: int = 20) -> Optional[dict]:
    trades = db.query_trades(max_trades)
    if not trades:
        return None
    today = dt.date.today()
    codes: Dict[str, List[dict]] = {}
    for t in trades:
        codes.setdefault(t["code"], []).append(t)

    stocks = []
    trade_rows = []
    for code, ts in codes.items():
        first = min(t["date"] for t in ts)
        start = dt.date.fromisoformat(first) - dt.timedelta(days=14)
        try:
            klines = eastmoney.fetch_daily_kline(code, start, today)
        except Exception:  # noqa: BLE001
            klines = []
        name = next((t["name"] for t in ts if t["name"]), code)
        for t in ts:
            row = {
                "日期": t["date"], "标的": name,
                "方向": "买入" if t["side"] == "buy" else "卖出",
                "价格": t["price"], "股数": t["qty"],
                "当时想法": t["note"] or "(未记录)",
            }
            row.update(_trade_stats(t, klines))
            trade_rows.append(row)
        stocks.append({
            "标的": name,
            "日K近30个交易日": [
                {"日": k["date"][5:], "收": k["close"], "涨%": k["pct"],
                 "换手%": k["turnover"]} for k in klines[-30:]],
            "近期新闻标题": _fetch_news_titles(code),
        })

    first_date = min(t["date"] for t in trades)
    moods = [m for m in db.query_mood(60) if m["date"] >= first_date][-15:]
    return {
        "交易记录": sorted(trade_rows, key=lambda r: r["日期"]),
        "标的行情与消息": stocks,
        "交易时段市场情绪": [
            {"日期": m["date"], "上涨": m["up_count"], "下跌": m["down_count"],
             "涨停": m["zt_count"], "炸板率": "{:.0%}".format(m["blast_rate"]),
             "连板高度": m["max_boards"],
             "成交额亿": round(m["amount"] / 1e8)} for m in moods],
        "说明": "市场情绪仅覆盖本系统开始归档之后的日期,更早的交易缺少情绪数据属正常",
    }


def generate_trade_review() -> str:
    payload = build_trade_review_input()
    if payload is None:
        raise ValueError("尚无交易记录,请先在「我的复盘」录入")
    import json
    return chat([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ], temperature=0.3)
