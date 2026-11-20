# -*- coding: utf-8 -*-
"""运行时装配：把 配置 / 记忆 / 工具 / 技能 / 插件 / MCP / 模型 组装成一个 Agent。"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from .agent import Agent, AgentContext
from .builtin import register_builtins
from .config import DEFAULT_HOME, Config
from .kernel import Kernel
from .llm import create_llm
from .mcp import MCPManager
from .memory import Memory
from .mode import apply_mode, mode_catalog, normalize_mode
from .models import ModelRegistry
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

        # ── 插件化内核：服务定位 + 可拦截事件链 + 分段提示词 ──
        self.kernel = Kernel()
        # 配置跟随 rt.home：默认就是 ~/.miniagent，测试/--home 时自动隔离
        self.config_path = os.path.join(self.home, "config.json")
        # 让 onboarding.apply_setup / check_setup 也写同一个位置
        cfg.config_target = self.config_path
        self.models = ModelRegistry(cfg, config_path=self.config_path)
        self._register_services()

        # 当前生效模型的配置视图；旧配置（只有四个标量）会自动包装成一条默认模型，
        # 因此 create_llm 拿到的值与改造前完全一致。
        active_view = self.models.resolve()
        self._llm_script = llm_script
        self.llm = create_llm(active_view or cfg, script=llm_script)
        self.agent: Optional[Agent] = None
        self.ctx: Optional[AgentContext] = None
        self.plugins: Optional[PluginManager] = None
        self.builtin_tools: List[str] = []
        self.mcp_tools: Dict[str, List[str]] = {}

    def _register_services(self) -> None:
        """把已有能力登记为内核服务，插件按名字取用，不互相硬引用。"""
        k = self.kernel
        k.provide("config", self.cfg)
        k.provide("models", self.models)
        k.provide("registry", self.registry)
        k.provide("memory", self.memory)
        k.provide("skills", self.skills)
        k.provide("mcp", self.mcp)
        k.provide("home", self.home)
        # 基础人格段：与 config.system_prompt 等价，但由内核统一分段合成
        k.section("persona", str(self.cfg.get("system_prompt", "")).strip(), order=0)

    def rebuild_llm(self) -> None:
        """切模型后重建后端，并同步内核服务与 Agent 引用。"""
        view = self.models.resolve()
        self.llm = create_llm(view or self.cfg,
                              script=getattr(self, "_llm_script", None))
        self.kernel.provide("llm", self.llm)
        if self.agent:
            self.agent.llm = self.llm

    # ── 统一切换入口（CLI / WebUI / 桌面窗口共用）──────────────
    def model_catalog(self) -> Dict[str, Any]:
        return self.models.catalog()

    def use_model(self, mid: str) -> Dict[str, Any]:
        result = self.models.set_active(mid)
        if result.get("ok"):
            self.rebuild_llm()
        return result

    def save_model(self, item: Dict[str, Any]) -> Dict[str, Any]:
        result = self.models.upsert(item)
        if result.get("ok"):
            self.rebuild_llm()
        return result

    def remove_model(self, mid: str) -> Dict[str, Any]:
        result = self.models.remove(mid)
        if result.get("ok"):
            self.rebuild_llm()
        return result

    def toggle_model(self, mid: str, enabled: bool) -> Dict[str, Any]:
        result = self.models.toggle(mid, enabled)
        if result.get("ok"):
            self.rebuild_llm()
        return result

    def mode_catalog(self) -> Dict[str, Any]:
        return mode_catalog(getattr(self, "mode", "standard"))

    def set_mode(self, name: str) -> Dict[str, Any]:
        key = normalize_mode(name)
        apply_mode(self.kernel, self.cfg, key)
        self.mode = key
        self.cfg.set("mode", key)
        if self.agent:
            self.agent.max_steps = int(self.cfg.get("max_steps", 24))
        return {"ok": True, "message": "已切换到「%s」模式" % key,
                "catalog": self.mode_catalog()}

    def kernel_status(self) -> Dict[str, Any]:
        return {"services": self.kernel.service_names(),
                "sections": self.kernel.section_names(),
                "slots": self.kernel.slot_names(),
                "plugins": self.kernel.plugin_names()}

    def build(self) -> Agent:
        cfg = self.cfg
        cfg.set("workspace", os.path.abspath(cfg.get("workspace", ".")))
        # 模式段要在 Agent 构造前登记：max_steps 在 Agent.__init__ 时读取
        self.mode = normalize_mode(cfg.get("mode", "standard"))
        apply_mode(self.kernel, cfg, self.mode)
        self.agent = Agent(cfg, self.registry, self.llm, self.memory,
                           skills=self.skills, mcp=self.mcp)
        self.agent.kernel = self.kernel
        self.ctx = AgentContext(self.agent)
        self.kernel.provide("agent", self.agent)
        self.kernel.provide("llm", self.llm)
        self.kernel.startup()

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
        cat = self.models.catalog()
        lines = [
            "当前模型: %s (%s @ %s)" % (self.cfg.get("model"), self.cfg.get("provider"),
                                        self.cfg.get("api_base") or "-"),
            "模型目录: %d 个，当前 %s" % (cat["count"], cat["active_model"] or "-"),
            "内核服务: %s" % ", ".join(self.kernel.service_names()),
            "提示词段: %s" % (", ".join(self.kernel.section_names()) or "-"),
            "工作区:   %s" % os.path.abspath(self.cfg.get("workspace", ".")),
            "数据:     %s" % self.home,
            "工具:     %d 个" % len(self.registry.names()),
            "技能:     %d 个" % len(self.skills.names()),
            "插件:     %s" % (self.plugins.summary().replace("\n", " | ") if self.plugins else "-"),
            "MCP:      %s" % self.mcp.summary().replace("\n", " | "),
        ]
        return "\n".join(lines)

    def shutdown(self) -> None:
        try:
            self.kernel.dispose()
        except Exception:
            pass
        try:
            self.mcp.shutdown()
        except Exception:
            pass
