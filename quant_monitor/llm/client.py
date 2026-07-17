"""OpenAI 兼容风格的统一 LLM 客户端。

DeepSeek / Qwen(DashScope) / GLM / Claude 兼容端点均可,
在 config.yaml 的 llm 段配置 base_url + api_key + model 即可切换。
设计约束见 docs/AI_LAYER.md:本模块只做文本生成,系统中不存在
任何"LLM 输出 → 交易执行"的调用路径。
"""

from __future__ import annotations

from typing import List

import requests

from quant_monitor.config import CONFIG


class LLMDisabled(RuntimeError):
    pass


def llm_enabled() -> bool:
    cfg = CONFIG.get("llm") or {}
    return bool(cfg.get("enabled")) and bool(cfg.get("api_key"))


def chat(messages: List[dict], temperature: float = 0.4) -> str:
    """调用 chat/completions,返回文本。未启用时抛 LLMDisabled。

    走系统默认网络环境(不做直连豁免):国内模型商直连即可,
    海外端点则可借助用户的加速器。
    """
    cfg = CONFIG.get("llm") or {}
    if not llm_enabled():
        raise LLMDisabled(
            "AI 功能未启用:请在 config.yaml 的 llm 段填入 api_key 并设 enabled: true")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    resp = requests.post(
        url,
        json={
            "model": cfg["model"],
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        },
        headers={"Authorization": "Bearer {}".format(cfg["api_key"])},
        timeout=cfg.get("timeout", 90),
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
