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

## 快速开始（当前阶段：M0 之前的数据源验证）

```bash
pip install -r requirements.txt
python scripts/check_datasources.py
```

体检脚本会逐一验证东财/腾讯/新浪/akshare 各接口并输出 ✅/❌ 汇总。
把结果反馈给协作 AI，即可开工里程碑 M0（项目地基）。

## 当前进度

- [x] 规划：任务拆解 / 技术路线 / 数据源方案
- [x] 数据源体检脚本
- [ ] M0 地基：数据接入层 + 调度器 + 存储 + Web 骨架
- [ ] M1 盘后复盘
- [ ] M2 盘前简报
- [ ] M3 盘中实时监控与异动警报

## 历史代码

`monitor.py` 为旧版新闻关键词过滤 MVP，其逻辑将在 M2 阶段迁移为盘前模块的一部分。
