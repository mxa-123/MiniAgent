# -*- coding: utf-8 -*-
"""运行时装配：把 配置 / 记忆 / 工具 / 技能 / 插件 / MCP / 模型 组装成一个 Agent。"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from .agent import Agent, AgentContext
from .builtin import register_builtins
from .config import DEFAULT_HOME, Config
from .llm import create_llm
from .mcp import MCPManager
from .memory import Memory
from .plugins import PluginManager
from .skills import Skills
from .tools import Registry
from .util import LOG

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pick_dir(cfg_value: str, fallback_name: str) -> str:
    """优先用配置值；相对路径按项目根解析；不存在则退回 ~/.miniagent/<name>。"""
    if cfg_value:
        p = cfg_value if os.path.isabs(cfg_value) else os.path.join(ROOT, cfg_value)
        return os.path.abspath(p)
    return os.path.join(DEFAULT_HOME, fallback_name)


class Runtime(object):
    def __init__(self, cfg: Config, home: Optional[str] = None, session: Optional[str] = None,
                 llm_script=None):
        self.cfg = cfg
        self.home = os.path.abspath(home or DEFAULT_HOME)
        self.registry = Registry()
        self.memory = Memory(self.home, session=session,
                             max_history=int(cfg.get("max_history", 40)))
        self.skills = Skills(_pick_dir(str(cfg.get("skills_dir", "skills")), "skills"))
        self.mcp = MCPManager(cfg.get("mcpServers") or {})
        self.llm = create_llm(cfg, script=llm_script)
        self.agent: Optional[Agent] = None
        self.ctx: Optional[AgentContext] = None
        self.plugins: Optional[PluginManager] = None
        self.builtin_tools: List[str] = []
        self.mcp_tools: Dict[str, List[str]] = {}

    def build(self) -> Agent:
        cfg = self.cfg
        cfg.set("workspace", os.path.abspath(cfg.get("workspace", ".")))
        self.agent = Agent(cfg, self.registry, self.llm, self.memory,
                           skills=self.skills, mcp=self.mcp)
        self.ctx = AgentContext(self.agent)

        if cfg.get("enable_builtin_tools", True):
            self.builtin_tools = register_builtins(self.registry, self.ctx)

        loaded = self.skills.load()
        if loaded:
            self.skills.register_tool(self.registry, self.agent)

        self.plugins = PluginManager(_pick_dir(str(cfg.get("plugins_dir", "plugins")), "plugins"),
                                     self.registry, self.ctx)
        self.plugins.load_all()

        if cfg.get("mcpServers"):
            self.mcp_tools = self.mcp.connect_all(self.registry)

        LOG.info("运行时就绪：工具 %d 个（内置 %d / 技能 %d / MCP %d）",
                 len(self.registry.names()), len(self.builtin_tools),
                 len(self.skills.names()), sum(len(v) for v in self.mcp_tools.values()))
        return self.agent

    def reload_extensions(self) -> str:
        """热重载技能与插件（工具表会重建）。"""
        keep = self.registry.names()
        self.registry = Registry()
        if self.agent:
            self.agent.registry = self.registry
        if self.ctx:
            self.ctx.registry = self.registry
        if self.cfg.get("enable_builtin_tools", True) and self.ctx:
            register_builtins(self.registry, self.ctx)
        self.skills.load()
        self.skills.register_tool(self.registry, self.agent)
        if self.plugins and self.ctx:
            self.plugins.registry = self.registry
            self.plugins.load_all()
        return "已重载：%d 个工具（原 %d）" % (len(self.registry.names()), len(keep))

    def status(self) -> str:
        lines = [
            "模型:   %s (%s @ %s)" % (self.cfg.get("model"), self.cfg.get("provider"),
                                      self.cfg.get("api_base") or "-"),
            "工作区: %s" % os.path.abspath(self.cfg.get("workspace", ".")),
            "数据:   %s" % self.home,
            "工具:   %d 个" % len(self.registry.names()),
            "技能:   %d 个" % len(self.skills.names()),
            "插件:   %s" % (self.plugins.summary().replace("\n", " | ") if self.plugins else "-"),
            "MCP:    %s" % self.mcp.summary().replace("\n", " | "),
        ]
        return "\n".join(lines)

    def shutdown(self) -> None:
        try:
            self.mcp.shutdown()
        except Exception:
            pass
