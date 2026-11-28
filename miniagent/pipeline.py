# -*- coding: utf-8 -*-
"""Pipeline：把 Planner 与 Executor 串成一条可直接使用的「规划-执行-反馈」流水线。

对应 DSH 的分层思想：
    目标 → Planner → Task → Executor → 工具调用 → history → 结果

对外只给一个 PlanRunner，内部复用既有 Kernel / Registry / LLM，不重复造轮子。
仅依赖标准库；语法兼容 Python 3.7（Win7 便携包）。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .executor import Executor
from .kernel import Task
from .planner import Planner

EVENT_PLAN = "agent.plan"


class PlanRunner(object):
    """规划 + 执行的一站式入口。"""

    def __init__(self, registry: Any, llm: Any = None, kernel: Any = None,
                 on_step: Optional[Callable[[Dict[str, Any]], None]] = None,
                 default_action: str = "run_command",
                 max_steps: int = 50):
        self.registry = registry
        self.kernel = kernel
        self.planner = Planner(llm=llm,
                               tool_names=list(registry.names()) if registry else [],
                               default_action=default_action)
        self.executor = Executor(registry=registry, max_steps=max_steps,
                                 on_step=on_step)

    # ── 事件 ───────────────────────────────────────────────────
    def _emit(self, kind: str, payload: Dict[str, Any]) -> None:
        if self.kernel is None:
            return
        try:
            self.kernel.emit(EVENT_PLAN, {"kind": kind, "payload": payload})
        except Exception:
            pass

    # ── 主流程 ─────────────────────────────────────────────────
    def plan_only(self, goal: str) -> Task:
        """只规划不执行，用于「给我看看计划」。"""
        task = self.planner.plan(goal)
        self._emit("planned", {"goal": task.goal, "steps": task.steps})
        return task

    def run(self, goal: str, retries: int = 1,
            auto_replan: bool = True) -> Dict[str, Any]:
        """规划 → 执行 → 失败则重新规划再试一轮。返回结构化结果。"""
        task = self.plan_only(goal)
        result = self.executor.run_plan(task, retries=retries)
        if not result.get("ok") and auto_replan:
            self._emit("replan", {"goal": goal, "failed_at":
                                  result.get("steps", [{}])[0].get("desc")})
            task2 = self.planner.replan(task)
            self._emit("planned", {"goal": task2.goal, "steps": task2.steps})
            result2 = self.executor.run_plan(task2, retries=retries)
            result2["replanned"] = True
            result2["first_attempt"] = result
            result = result2
        else:
            result["replanned"] = False
        self._emit("done", {"ok": result.get("ok"), "status": result.get("status")})
        return result

    # ── 展示辅助 ───────────────────────────────────────────────
    @staticmethod
    def format_result(result: Dict[str, Any]) -> str:
        lines = ["目标: %s" % result.get("goal", ""),
                 "状态: %s%s" % (result.get("status", "?"),
                                 "（已重新规划）" if result.get("replanned") else "")]
        for s in result.get("steps", []):
            mark = {"OK": "[√]", "FAILED": "[×]", "RUNNING": "[…]"}.get(s.get("status"), "[ ]")
            lines.append("  %s %s -> %s" % (mark, s.get("desc"), s.get("action")))
            if s.get("error"):
                lines.append("      错误: %s" % str(s["error"])[:200])
            elif s.get("result"):
                lines.append("      结果: %s" % str(s["result"])[:200])
        return "\n".join(lines)
