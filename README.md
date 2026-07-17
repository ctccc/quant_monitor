# Quant Monitor · A 股量化短线盯盘工作站

服务于 A 股超短线/动能交易的个人决策沙盘：**盘前给简报、盘中报异动、盘后做复盘**。
全部数据来自免费公开接口，零付费、零权限依赖，单机单进程运行。

> ⚠️ 仅供个人研究学习，不构成投资建议。超短线交易风险极高。

## 文档导航

| 文档 | 内容 |
|------|------|
| [docs/PLAN.md](docs/PLAN.md) | 需求拆解、功能清单（P0–P4）、里程碑路线图、风险对策 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 技术架构、选型理由、数据接入层设计、目录规划 |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | 免费数据源调研、接口清单、功能↔数据映射、能力边界 |
| [docs/AI_LAYER.md](docs/AI_LAYER.md) | AI 参谋层：LLM 快慢分层设计、防幻觉铁律、模型接入（融合 trading agent 思路） |

## 快速开始

```bash
python3 -m pip install -r requirements.txt   # 首次或依赖更新时
python3 -m quant_monitor                     # 启动看板
```

浏览器打开 **http://127.0.0.1:8000**，点右上角「立即归档今日数据」抓取当日
涨停池与板块资金流。交易日 15:10 调度器也会自动归档（应用需处于运行状态）。

其他命令：

```bash
python3 -m quant_monitor archive       # 不开看板,只执行一次归档
python3 scripts/check_datasources.py   # 数据源体检(接口异常时先跑这个)
```

## 当前进度

- [x] 规划：任务拆解 / 技术路线 / 数据源方案 / AI 参谋层设计
- [x] 数据源体检脚本（用户实测 12/12 通过）
- [x] M0 地基：数据接入层（直连+镜像轮换+限速）/ SQLite 存储 / 调度器 / 看板骨架
- [x] M1 盘后复盘（核心）：情绪面板与近10日历史 / 连板梯队 / 涨停行业分布 /
      板块资金5日累计 / 炸板与跌停池采集 / 复盘笔记
- [x] 我的复盘：交易记录录入 / 持仓自动聚合与盈亏估值（腾讯行情）
- [x] M5a AI 复盘摘要：LLM 读当日结构化数据生成复盘叙事草稿
      （config.yaml 配置 api_key 启用,支持 DeepSeek/Qwen 等 OpenAI 兼容端点）
- [ ] M1 收尾：龙虎榜
- [ ] M2 盘前简报
- [ ] M3 盘中实时监控与异动警报

## 历史代码

`monitor.py` 为旧版新闻关键词过滤 MVP，其逻辑将在 M2 阶段迁移为盘前模块的一部分。
