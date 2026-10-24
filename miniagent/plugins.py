# -*- coding: utf-8 -*-
"""插件系统：把一个 .py 文件丢进 plugins/ 目录即可扩展工具。

插件写法（两种，任选）：
1) 用 @tool 装饰器，自动被扫描收集：
       from miniagent.tools import tool
       @tool(description="查天气")
       def weather(city: str) -> str:
           '''查询天气。:param city: 城市名'''
           return "晴"
2) 定义 setup(ctx)，自己注册（可以用 ctx.cfg / ctx.memory / ctx.emit）：
       def setup(ctx):
           ctx.registry.register_func(my_func, risky=True)
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from typing import Any, Dict, List, Optional

from .tools import collect_from_module
from .util import LOG


class LoadedPlugin(object):
    def __init__(self, name: str, path: str, ok: bool, tools: Optional[List[str]] = None, error: str = ""):
        self.name = name
        self.path = path
        self.ok = ok
        self.tools = tools or []
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover
        status = "OK" if self.ok else "FAIL"
        return "<Plugin %s %s tools=%s>" % (self.name, status, self.tools)


class PluginManager(object):
    def __init__(self, directory: str, registry, ctx):
        self.directory = os.path.abspath(directory) if directory else ""
        self.registry = registry
        self.ctx = ctx
        self.loaded: List[LoadedPlugin] = []

    def load_all(self) -> List[LoadedPlugin]:
        self.loaded = []
        if not self.directory or not os.path.isdir(self.directory):
            LOG.info("插件目录不存在: %s", self.directory)
            return self.loaded
        for fn in sorted(os.listdir(self.directory)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            path = os.path.join(self.directory, fn)
            self.loaded.append(self.load_file(path))
        return self.loaded

    def load_file(self, path: str) -> LoadedPlugin:
        name = os.path.splitext(os.path.basename(path))[0]
        before = set(self.registry.names())
        try:
            mod = _import_path(name, path)
            added: List[str] = []
            for t in collect_from_module(mod, source="plugin:" + name):
                self.registry.register(t)
                added.append(t.name)
            setup = getattr(mod, "setup", None)
            if callable(setup):
                setup(self.ctx)
            added += [n for n in self.registry.names() if n not in before]
            added = sorted(set(added))
            LOG.info("插件 %s 加载成功，工具: %s", name, added)
            return LoadedPlugin(name, path, True, added)
        except Exception as exc:
            LOG.warning("插件 %s 加载失败: %s\n%s", name, exc, traceback.format_exc(limit=3))
            return LoadedPlugin(name, path, False, [], "%s: %s" % (type(exc).__name__, exc))

    def summary(self) -> str:
        if not self.loaded:
            return "（无插件）"
        return "\n".join(
            "- %s [%s] %s" % (p.name, "OK" if p.ok else "FAIL",
                              (", ".join(p.tools) if p.ok else p.error))
            for p in self.loaded
        )


def _import_path(name: str, path: str):
    """按文件路径导入模块（Python 3.8 可用）。"""
    mod_name = "miniagent_plugin_" + name
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("无法导入: %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return module
