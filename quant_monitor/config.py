"""配置加载：仓库根目录的 config.yaml，缺失项自动使用默认值。"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"
DATA_DIR = ROOT / "data"

DEFAULTS = {
    "web": {"host": "127.0.0.1", "port": 8000},
    "datasource": {
        "timeout": 15,       # 单请求超时(秒)
        "max_per_sec": 5,    # 全局限速:每秒最多请求数
        "retries": 1,        # 单接口失败后的重试次数
    },
    "archive": {
        "hour": 15,          # 盘后归档任务触发时间(交易日)
        "minute": 10,
    },
    "llm": {
        "enabled": False,    # 填好 api_key 后改 true 即启用 AI 复盘摘要
        "base_url": "https://api.deepseek.com",  # OpenAI 兼容端点均可
        "model": "deepseek-chat",
        "api_key": "",
        "timeout": 90,
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    user_cfg = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
    return _merge(DEFAULTS, user_cfg)


CONFIG = load_config()
