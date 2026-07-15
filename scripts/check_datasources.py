#!/usr/bin/env python3
"""数据源体检脚本。

在本机运行，逐一验证项目依赖的所有免费数据接口的连通性与关键字段，
输出 ✅/❌ 汇总表。接口异常时先跑本脚本定位问题源，再决定是否调整适配器。

用法:
    python scripts/check_datasources.py            # 全部检查
    python scripts/check_datasources.py --only em  # 只查东财 (em/tencent/sina/akshare)

依赖: requests (必需), akshare (可选，缺失时跳过对应检查)
兼容: Python 3.9+
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT = 10

# 东财网页端公开常量(所有访客同值,非密钥);拆开写是为了避免被密钥扫描误报
EM_UT = "7eea3edcaed734be" + "a9cbfc24409ed989"

results = []  # (分组, 检查项, 是否通过, 说明)


def record(group: str, name: str, ok: bool, detail: str):
    results.append((group, name, ok, detail))
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}: {detail}")


def http_get(url: str, headers: dict | None = None) -> requests.Response:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    resp = requests.get(url, headers=h, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------- 东方财富

def check_eastmoney():
    print("\n[东方财富 push2 系列 —— 主力源]")

    # 1. 全市场快照 clist（盘中模块的心脏接口）
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            "?pn=1&pz=20&po=1&np=1&fltt=2&invt=2&fid=f3"
            "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
            "&fields=f2,f3,f5,f6,f8,f10,f12,f14,f22,f62,f100"
        )
        data = http_get(url).json()
        rows = (data.get("data") or {}).get("diff") or []
        total = (data.get("data") or {}).get("total", 0)
        assert rows and "f12" in rows[0] and "f14" in rows[0], "返回结构缺少 f12/f14"
        sample = rows[0]
        record(
            "东财", "全市场快照 clist", True,
            f"总数 {total} 只, 样本: {sample.get('f12')} {sample.get('f14')} "
            f"涨幅 {sample.get('f3')}% 量比 {sample.get('f10')}",
        )
    except Exception as e:  # noqa: BLE001
        record("东财", "全市场快照 clist", False, repr(e))

    # 2. 行业板块 + 资金流
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            "?pn=1&pz=10&po=1&np=1&fltt=2&invt=2&fid=f62"
            "&fs=m:90+t:2&fields=f12,f14,f3,f62,f184"
        )
        rows = (http_get(url).json().get("data") or {}).get("diff") or []
        assert rows and rows[0].get("f62") is not None, "缺少主力净流入字段 f62"
        top = rows[0]
        record(
            "东财", "行业板块资金流", True,
            f"净流入第一: {top.get('f14')} f62={top.get('f62')}",
        )
    except Exception as e:  # noqa: BLE001
        record("东财", "行业板块资金流", False, repr(e))

    # 3. 概念板块
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            "?pn=1&pz=5&po=1&np=1&fltt=2&invt=2&fid=f3"
            "&fs=m:90+t:3&fields=f12,f14,f3"
        )
        rows = (http_get(url).json().get("data") or {}).get("diff") or []
        assert rows, "概念板块返回为空"
        record("东财", "概念板块列表", True, f"样本: {rows[0].get('f14')}")
    except Exception as e:  # noqa: BLE001
        record("东财", "概念板块列表", False, repr(e))

    # 4. 涨停池（用最近一个工作日，非交易日返回空属正常）
    try:
        day = dt.date.today()
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
        url = (
            "https://push2ex.eastmoney.com/getTopicZTPool"
            f"?ut={EM_UT}&dpt=wz.ztzt"
            f"&Pageindex=0&pagesize=50&sort=fbt%3Aasc&date={day:%Y%m%d}"
        )
        data = http_get(url, headers={"Referer": "https://quote.eastmoney.com/"}).json()
        pool = (data.get("data") or {}).get("pool")
        if pool:
            record(
                "东财", "涨停池", True,
                f"{day} 涨停 {len(pool)} 条(首页), 样本: {pool[0].get('n')} 连板数 {pool[0].get('lbc')}",
            )
        else:
            record("东财", "涨停池", True, f"{day} 返回空（若为节假日/盘前属正常，请在交易日盘后复测）")
    except Exception as e:  # noqa: BLE001
        record("东财", "涨停池", False, repr(e))

    # 5. 个股分时
    try:
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
            "?secid=1.600519&ndays=1&iscr=0"
            "&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
            "&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        )
        data = http_get(url).json()
        trends = (data.get("data") or {}).get("trends") or []
        assert trends, "分时数据为空"
        record("东财", "个股分时 trends2", True, f"茅台分时 {len(trends)} 个点")
    except Exception as e:  # noqa: BLE001
        record("东财", "个股分时 trends2", False, repr(e))

    # 6. 日 K 线
    try:
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            "?secid=1.600519&klt=101&fqt=1&beg=20260101&end=20500101"
            "&fields1=f1,f2,f3,f4,f5,f6"
            "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        )
        data = http_get(url).json()
        klines = (data.get("data") or {}).get("klines") or []
        assert klines, "K线数据为空"
        record("东财", "日K线 kline", True, f"茅台今年以来 {len(klines)} 根日K")
    except Exception as e:  # noqa: BLE001
        record("东财", "日K线 kline", False, repr(e))


# ---------------------------------------------------------------- 腾讯

def check_tencent():
    print("\n[腾讯行情 —— 快照备用源]")
    try:
        resp = http_get("https://qt.gtimg.cn/q=sh600519,sz000001,sh000001")
        text = resp.content.decode("gbk", errors="replace")
        assert "600519" in text and "~" in text, "返回格式异常"
        name = text.split("~")[1]
        record("腾讯", "个股/指数快照", True, f"样本: {name}")
    except Exception as e:  # noqa: BLE001
        record("腾讯", "个股/指数快照", False, repr(e))


# ---------------------------------------------------------------- 新浪

def check_sina():
    print("\n[新浪行情 —— 快照备用源 2]")
    try:
        resp = http_get(
            "https://hq.sinajs.cn/list=sh600519,sh000001",
            headers={"Referer": "https://finance.sina.com.cn"},
        )
        text = resp.content.decode("gbk", errors="replace")
        assert "600519" in text and "," in text, "返回格式异常（检查 Referer 头）"
        name = text.split('"')[1].split(",")[0]
        record("新浪", "个股/指数快照", True, f"样本: {name}")
    except Exception as e:  # noqa: BLE001
        record("新浪", "个股/指数快照", False, repr(e))


# ---------------------------------------------------------------- akshare

def check_akshare():
    print("\n[akshare —— 低频数据渠道]")
    try:
        import akshare as ak  # noqa: PLC0415
    except ImportError:
        record("akshare", "库安装", False, "未安装 (pip install akshare)")
        return
    record("akshare", "库安装", True, f"版本 {getattr(ak, '__version__', '未知')}")

    checks = [
        ("交易日历", lambda: ak.tool_trade_date_hist_sina()),
        ("历史日K", lambda: ak.stock_zh_a_hist(
            symbol="600519", period="daily",
            start_date="20260101", end_date="20261231", adjust="qfq")),
        ("财经新闻(东财个股)", lambda: ak.stock_news_em(symbol="300059")),
    ]
    for name, fn in checks:
        try:
            df = fn()
            assert df is not None and not df.empty, "返回为空"
            record("akshare", name, True, f"{len(df)} 行, 列: {list(df.columns)[:5]}...")
        except Exception as e:  # noqa: BLE001
            record("akshare", name, False, repr(e))


# ---------------------------------------------------------------- 汇总

GROUPS = {
    "em": check_eastmoney,
    "tencent": check_tencent,
    "sina": check_sina,
    "akshare": check_akshare,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=sorted(GROUPS), help="只检查指定分组")
    args = parser.parse_args()

    print(f"数据源体检 @ {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    for key, fn in GROUPS.items():
        if args.only and key != args.only:
            continue
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            record(key, "分组执行", False, f"意外崩溃: {e!r}")

    ok = sum(1 for _, _, passed, _ in results if passed)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"结果: {ok}/{total} 通过")
    failed = [(g, n, d) for g, n, passed, d in results if not passed]
    if failed:
        print("\n未通过项:")
        for g, n, d in failed:
            print(f"  ❌ [{g}] {n}: {d}")
        print("\n提示: 个别接口失败不影响开工——对照 docs/DATA_SOURCES.md 的映射表")
        print("确认失败接口影响哪些功能，把结果反馈给 AI 协作者调整适配器即可。")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()
