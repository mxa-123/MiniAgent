# -*- coding: utf-8 -*-
"""插件化微内核：服务定位 + 可拦截事件链 + 可卸载副作用 + 槽位 + 分段提示词。

设计灵感来自「一切皆插件」的分层架构思想（参考开源项目 DeepSeek Harness 的公开设计思路；对方许可证以其仓库声明为准）。
本文件为独立编写的实现，未使用、未复制任何第三方项目的源码、常量或文案。

对外只依赖 Python 标准库；语法兼容 3.7 / 3.8（Win7 便携包）。

五个能力：
  1. 服务定位：provide / get，插件按名字取依赖，不互相硬引用。
  2. 事件链：on / emit，监听者可拦截并改写本次调用的载荷（洋葱模型）。
  3. 可卸载副作用：effect / inject / on / section / slot 都返回卸载句柄；
     插件装载期间的注册物自动归属该插件，卸载时统一撤销。
  4. 槽位：slot / contributions，界面由多方贡献后统一渲染。
  5. 分段提示词：section / compose_prompt，按 order 合成系统提示词。
"""

from __future__ import annotations

import inspect
import itertools
from typing import Any, Callable, Dict, List, Optional, Tuple

from .util import LOG

# 事件名用点号分隔，区别于任何第三方项目的命名习惯。
EVENT_REQUEST = "agent.request"
EVENT_PROMPT = "prompt.compose"
EVENT_STARTUP = "kernel.startup"
EVENT_SHUTDOWN = "kernel.shutdown"


class Disposer(object):
    """卸载句柄：调用一次即撤销注册，重复调用安全。"""

    def __init__(self, fn: Optional[Callable[[], None]]):
        self._fn = fn
        self._done = False

    def __call__(self) -> None:
        if self._done:
            return
        self._done = True
        if self._fn:
            try:
                self._fn()
            except Exception as exc:
                LOG.warning("副作用清理失败: %s", exc)

    @property
    def disposed(self) -> bool:
        return self._done


class Plugin(object):
    """插件基类：子类声明 name / 依赖 / apply(ctx)，由内核负责装配与卸载。

    apply 收到的 ctx 就是内核本身，可直接调用 get / on / section / slot / effect。
    这些调用产生的注册物会自动挂到本插件名下，卸载时一并撤销。
    """

    name = ""
    inject: Tuple[str, ...] = ()

    def apply(self, ctx: "Kernel") -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        pass


class Kernel(object):
    """极简插件宿主。所有注册动作都返回 Disposer，便于整体卸载。"""

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}
        self._handlers: Dict[str, List[Dict[str, Any]]] = {}
        self._slots: Dict[str, List[Dict[str, Any]]] = {}
        self._sections: List[Dict[str, Any]] = []
        self._plugins: Dict[str, Dict[str, Any]] = {}
        self._seq = itertools.count()
        self._owner_stack: List[List[Disposer]] = []
        self._disposed = False

    def _own(self, d: Disposer) -> Disposer:
        if self._owner_stack:
            self._owner_stack[-1].append(d)
        return d

    # ── 1. 服务定位 ────────────────────────────────────────────
    def provide(self, name: str, service: Any) -> Disposer:
        """注册服务；撤销时恢复原值或删除。"""
        had = name in self._services
        old = self._services.get(name)
        self._services[name] = service

        def undo() -> None:
            if had:
                self._services[name] = old
            else:
                self._services.pop(name, None)

        return self._own(Disposer(undo))

    def get(self, name: str, default: Any = None) -> Any:
        return self._services.get(name, default)

    def require(self, name: str) -> Any:
        if name not in self._services:
            raise KeyError("缺少服务: %s" % name)
        return self._services[name]

    def service_names(self) -> List[str]:
        return sorted(self._services.keys())

    # ── 2. 事件链（洋葱模型，可拦截改写）──────────────────────
    def on(self, event: str, handler: Callable[..., Any],
           prepend: bool = False, priority: int = 100) -> Disposer:
        """注册监听者。

        - handler(payload, next) 视为拦截器：可改写载荷、可决定是否继续；
        - handler(payload) 视为观察者：只收通知，不改载荷。
        """
        try:
            intercept = len(inspect.signature(handler).parameters) >= 2
        except (TypeError, ValueError):
            intercept = False
        rec = {"fn": handler, "intercept": intercept,
               "order": (-1000 if prepend else priority), "seq": next(self._seq)}
        self._handlers.setdefault(event, []).append(rec)
        self._handlers[event].sort(key=lambda r: (r["order"], r["seq"]))

        def undo() -> None:
            try:
                self._handlers[event].remove(rec)
            except (ValueError, KeyError):
                pass

        return self._own(Disposer(undo))

    def emit(self, event: str, payload: Any = None) -> Any:
        """跑完整条链并返回最终载荷。单个监听者出错不炸整条链。"""
        handlers = list(self._handlers.get(event, []))

        def step(index: int, value: Any) -> Any:
            if index >= len(handlers):
                return value
            rec = handlers[index]
            fn = rec["fn"]
            if not rec["intercept"]:
                try:
                    fn(value)
                except Exception as exc:
                    LOG.warning("事件 %s 观察者异常: %s", event, exc)
                return step(index + 1, value)

            called = [False]
            downstream = [None]

            def nxt(next_value: Any = None) -> Any:
                called[0] = True
                result = step(index + 1, value if next_value is None else next_value)
                downstream[0] = result
                return result

            try:
                out = fn(value, nxt)
                if called[0]:
                    # 已调用 next：拦截器显式返回值优先，否则用链的下游结果
                    return downstream[0] if out is None else out
                # 未调用 next：拦截链在此终止（可用于短路）
                return value if out is None else out
            except Exception as exc:
                LOG.warning("事件 %s 拦截器异常: %s", event, exc)
                return step(index + 1, value)

        return step(0, payload)

    def has_listeners(self, event: str) -> bool:
        return bool(self._handlers.get(event))

    # ── 3. 可卸载副作用 / 依赖注入 ─────────────────────────────
    def effect(self, fn: Callable[..., Any]) -> Disposer:
        """立即执行 fn，其返回值若是可调用对象则作为清理函数。"""
        cleanup: Optional[Callable[[], None]] = None
        try:
            out = fn(self) if _takes_arg(fn) else fn()
            if callable(out):
                cleanup = out
        except Exception as exc:
            LOG.warning("副作用执行失败: %s", exc)
        return self._own(Disposer(cleanup))

    def inject(self, deps: Tuple[str, ...], fn: Callable[["Kernel"], Any]) -> Disposer:
        """依赖齐备才执行；缺依赖抛错，避免插件在半初始化状态下运行。"""
        missing = [d for d in deps if d not in self._services]
        if missing:
            raise KeyError("插件依赖未就绪: %s" % ", ".join(missing))
        return self.effect(fn)

    # ── 4. 槽位 ───────────────────────────────────────────────
    def slot(self, name: str, key: str, value: Any, order: int = 100) -> Disposer:
        """向命名槽位贡献一项内容，界面层自行决定如何渲染。"""
        rec = {"key": key, "value": value,
               "order": order, "seq": next(self._seq)}
        self._slots.setdefault(name, []).append(rec)
        self._slots[name].sort(key=lambda r: (r["order"], r["seq"]))

        def undo() -> None:
            try:
                self._slots[name].remove(rec)
            except (ValueError, KeyError):
                pass

        return self._own(Disposer(undo))

    def contributions(self, name: str) -> List[Any]:
        return [r["value"] for r in self._slots.get(name, [])]

    def slot_names(self) -> List[str]:
        return sorted(self._slots.keys())

    # ── 5. 分段提示词 ─────────────────────────────────────────
    def section(self, name: str, text: str, order: int = 100) -> Disposer:
        """贡献一段系统提示词；同名段覆盖，按 order 排序合成。"""
        for rec in self._sections:
            if rec["name"] == name:
                rec["text"] = text
                rec["order"] = order
                return Disposer(None)
        rec = {"name": name, "text": text, "order": order,
               "seq": next(self._seq)}
        self._sections.append(rec)

        def undo() -> None:
            try:
                self._sections.remove(rec)
            except (ValueError, KeyError):
                pass

        return self._own(Disposer(undo))

    def compose_prompt(self, base: str = "") -> str:
        """把分段按 order 拼成完整系统提示词；base 永远排最前。"""
        ordered = sorted(self._sections, key=lambda r: (r["order"], r["seq"]))
        parts = [base.strip()] if base and base.strip() else []
        for rec in ordered:
            t = str(rec["text"] or "").strip()
            if t:
                parts.append(t)
        return "\n\n".join(parts).strip()

    def section_names(self) -> List[str]:
        return [r["name"] for r in sorted(self._sections,
                                          key=lambda r: (r["order"], r["seq"]))]

    # ── 6. 插件装载 / 卸载 ────────────────────────────────────
    def load(self, plugin: Plugin) -> Disposer:
        """装配插件：检查依赖 → 收集其注册物 → 执行 apply。"""
        name = plugin.name or plugin.__class__.__name__
        if name in self._plugins:
            raise ValueError("插件已装载: %s" % name)
        deps = tuple(getattr(plugin, "inject", ()) or ())
        missing = [d for d in deps if d not in self._services]
        if missing:
            raise KeyError("插件 %s 依赖未就绪: %s" % (name, ", ".join(missing)))

        owned: List[Disposer] = []
        self._owner_stack.append(owned)
        try:
            plugin.apply(self)
        finally:
            self._owner_stack.pop()

        def undo() -> None:
            for d in reversed(owned):
                d()
            try:
                plugin.shutdown()
            except Exception as exc:
                LOG.warning("插件 %s 关闭异常: %s", name, exc)
            self._plugins.pop(name, None)

        holder = Disposer(undo)
        self._plugins[name] = {"plugin": plugin, "dispose": holder}
        return holder

    def unload(self, name: str) -> bool:
        rec = self._plugins.pop(name, None)
        if not rec:
            return False
        rec["dispose"]()
        return True

    def plugin_names(self) -> List[str]:
        return sorted(self._plugins.keys())

    # ── 7. 生命周期 ───────────────────────────────────────────
    def startup(self) -> None:
        self.emit(EVENT_STARTUP, {"kernel": self})

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self.emit(EVENT_SHUTDOWN, {"kernel": self})
        for name in list(self._plugins.keys()):
            self.unload(name)
        self._handlers.clear()
        self._slots.clear()
        self._sections.clear()
        self._services.clear()


def _takes_arg(fn: Callable[..., Any]) -> bool:
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False
