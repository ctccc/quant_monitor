"""AI 复盘摘要（M5a）:读本系统当日结构化数据,生成复盘叙事草稿。

防幻觉铁律(docs/AI_LAYER.md §3):
1. 输入只有本系统算好的 JSON,提示词明令禁止使用任何外部记忆数字;
2. 要求每条结论落在给定数据上;
3. 输出定位为"AI 参谋意见",由用户自行取舍,不触发任何动作。
"""

from __future__ import annotations

import json
from typing import Optional

from quant_monitor.llm.client import chat
from quant_monitor.store import db

_SYSTEM = """你是一名 A 股短线复盘参谋。你将收到一份 JSON,内含当日市场情绪指标、\
涨停梯队、涨停行业分布、板块资金流以及用户持仓表现,全部由用户本地系统实测汇总。

规则(必须遵守):
1. 只允许引用 JSON 里出现的数字与名称,严禁使用你训练记忆中的任何行情数据或新闻;
2. 数据里没有的信息,直接说"数据未覆盖",不要推测;
3. 输出为简洁的 markdown,分四节:「大盘情绪」「主线与梯队」「资金动向」「明日关注」;\
若 JSON 含持仓,追加「持仓提示」一节;
4. 每节 2~4 句,给判断也给依据(引用具体数字);
5. 结尾固定一行:"—— AI 参谋意见,仅供复盘参考,不构成投资建议"。"""


def build_review_input(date: str, positions: Optional[list] = None) -> dict:
    """汇集当日结构化事实。只取排名靠前的条目,控制 token 用量。"""
    zt = db.query_zt_pool(date)
    ladder = {}
    for it in zt:
        if it["boards"] >= 2:
            ladder.setdefault("{}板".format(it["boards"]), []).append(
                {"名称": it["name"], "行业": it["industry"],
                 "首封": it["first_seal"], "炸板次数": it["break_times"]})
    industry_count: dict = {}
    for it in zt:
        industry_count[it["industry"]] = industry_count.get(it["industry"], 0) + 1
    top_industries = sorted(industry_count.items(), key=lambda x: -x[1])[:8]

    moods = db.query_mood(6)
    flows = db.query_sector_flow(date, "industry", 10)
    concepts = db.query_sector_flow(date, "concept", 10)
    trend = sorted(db.query_sector_trend("industry", 5),
                   key=lambda x: -x["total_net"])[:8]

    payload = {
        "日期": date,
        "近几日情绪": [
            {"日期": m["date"], "上涨": m["up_count"], "下跌": m["down_count"],
             "涨停": m["zt_count"], "跌停": m["dt_count"],
             "炸板率": "{:.0%}".format(m["blast_rate"]),
             "连板高度": m["max_boards"],
             "成交额亿": round(m["amount"] / 1e8)} for m in moods
        ],
        "连板梯队": ladder,
        "涨停行业分布": [{"行业": k, "家数": v} for k, v in top_industries],
        "行业主力净流入前十_亿": [
            {"板块": f["name"], "净流入": round(f["main_net"] / 1e8, 2),
             "涨跌幅": f["pct"]} for f in flows],
        "概念主力净流入前十_亿": [
            {"板块": f["name"], "净流入": round(f["main_net"] / 1e8, 2),
             "涨跌幅": f["pct"]} for f in concepts],
        "行业5日累计净流入前八_亿": [
            {"板块": t["name"], "累计": round(t["total_net"] / 1e8, 2)}
            for t in trend],
    }
    if positions:
        payload["我的持仓"] = positions
    return payload


def generate_review(date: str, positions: Optional[list] = None) -> str:
    payload = build_review_input(date, positions)
    return chat([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ])
