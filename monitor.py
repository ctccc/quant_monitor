import akshare as ak

KEYWORDS = ["市场", "涨停", "重组", "半导体", "公司", "光通信", "芯片"]

def fetch_and_filter():
    try:
        df = ak.stock_news_em(symbol="东方财富网")
        print("当前数据包含的列名有：", df.columns)
        if df is None or df.empty:
            print("未获取到数据")
            return

        for _, row in df.iterrows():
            content = str(row.get("新闻内容", ""))
            time_str = str(row.get("发布时间", ""))
            title = str(row.get("新闻标题", ""))

            if any(kw in content for kw in KEYWORDS):
                print(f"\033[91m【{time_str}】{title} | {content}\033[0m")

        print("\n抓取完成")

    except Exception as e:
        print(f"抓取失败: {e}")

if __name__ == "__main__":
    fetch_and_filter()
