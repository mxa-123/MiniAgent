# -*- coding: utf-8 -*-
"""配置系统：JSON 文件 + 环境变量覆盖，零第三方依赖。"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

from .util import LOG, ensure_parent, read_text, write_text

DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".miniagent")

DEFAULTS: Dict[str, Any] = {
    # ── 模型 ──
    "provider": "openai_compat",   # openai_compat | ollama | mock
    "model": "deepseek-chat",
    "api_base": "https://api.deepseek.com/v1",
    "api_key": "",
    "temperature": 0.3,
    "max_tokens": 4096,
    "timeout": 120,
    "stream": True,
    "fallback_text_protocol": True,  # 模型不支持 function calling 时降级为 JSON 块协议
    # ── 行为 ──
    "system_prompt": "你是 MiniAgent（灵枢），一个务实、高效的本地 AI 助手。"
                     "用中文回答；先给结论再展开；不确定就说不确定，不编造。"
                     "能调用工具时优先调用工具拿到事实，再回答。",
    "max_steps": 24,               # 单轮最多工具调用轮次
    "max_tool_output": 8000,
    "workspace": ".",
    "confirm_tools": ["run_command", "write_file", "python_eval"],
    "auto_confirm": False,
    # ── 扩展 ──
    "plugins_dir": "plugins",
    "skills_dir": "skills",
    "enable_builtin_tools": True,
    "mcpServers": {},
    # ── 界面 ──
    "webui": {"host": "127.0.0.1", "port": 8787, "open_browser": True},
    "log_level": "INFO",
}

ENV_MAP = {
    "MINIAGENT_API_KEY": "api_key",
    "MINIAGENT_API_BASE": "api_base",
    "MINIAGENT_MODEL": "model",
    "MINIAGENT_PROVIDER": "provider",
}


class Config(object):
    """字典式配置，支持 cfg.get("a.b.c", default) 路径读取。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, path: Optional[str] = None):
        self._data = copy.deepcopy(DEFAULTS)
        if data:
            self._merge(self._data, data)
        self.path = path
        self.apply_env()

    # ── 基础存取 ──
    def apply_env(self) -> None:
        for env_key, cfg_key in ENV_MAP.items():
            val = os.environ.get(env_key)
            if val:
                self._data[cfg_key] = val

    def get(self, key: str, default: Any = None) -> Any:
        cur: Any = self._data
        for part in str(key).split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def set(self, key: str, value: Any) -> None:
        parts = str(key).split(".")
        cur: Dict[str, Any] = self._data
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value

    def as_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)

    def save(self, path: Optional[str] = None) -> str:
        target = path or self.path or os.path.join(DEFAULT_HOME, "config.json")
        ensure_parent(target)
        write_text(target, json.dumps(self._data, ensure_ascii=False, indent=2))
        return target

    # ── 加载 ──
    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        candidates: List[str] = []
        if path:
            candidates.append(path)
        else:
            candidates.append(os.path.join(os.getcwd(), "config", "config.json"))
            candidates.append(os.path.join(DEFAULT_HOME, "config.json"))
        for cand in candidates:
            if cand and os.path.isfile(cand):
                try:
                    data = json.loads(read_text(cand))
                    LOG.info("已加载配置: %s", cand)
                    return cls(data, path=cand)
                except Exception as exc:
                    LOG.warning("配置文件 %s 解析失败(%s)，改用默认配置", cand, exc)
        LOG.info("未找到配置文件，使用默认配置")
        return cls(None, path=(candidates[0] if candidates else None))

    @staticmethod
    def _merge(base: Dict[str, Any], new: Dict[str, Any]) -> None:
        for k, v in (new or {}).items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                Config._merge(base[k], v)
            else:
                base[k] = v
