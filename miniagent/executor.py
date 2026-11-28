# -*- coding: utf-8 -*-
"""Executor：驱动 Task 的步骤依次执行并回填结果。

设计要点（参考 DeepSeek Harness 的「规划-执行-反馈」循环思想，独立实现）：
  1. 每步把 step["action"] 交给工具注册表执行，参数取自 step["args"]；
  2. 单步失败可重试；重试耗尽则标记该步 FAILED 并中止任务；
  3. 每步结果写入 task.history，供 Planner 做自我修正；
  4. 可选 on_step 回调，把执行进度实时推给界面（流式）。

仅依赖标准库；语法兼容 Python 3.7 / 3.8（Win7 便携包）。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from .kernel import Task
from .util import LOG

_ERROR_MARKERS = ("错误：", "错误:", "异常：", "异常:", "traceback")


class Executor(object):
    """按序执行 Task 的步骤。"""

    def __init__(self, registry: Any, max_steps: int = 50,
                 on_step: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        registry: 需提供 execute(name, arguments) -> str 的对象（如 tools.Registry）。
        """
        self.registry = registry
        self.max_steps = max_steps
        self.on_step = on_step

    # ── 内部 ───────────────────────────────────────────────────
    def _notify(self, payload: Dict[str, Any]) -> None:
        if self.on_step is None:
            return
        try:
            self.on_step(payload)
        except Exception as exc:
            LOG.warning("on_step 回调异常: %s", exc)

    @staticmethod
    def _is_error(text: str) -> bool:
        low = (text or "").lower()
        return any(m in low for m in _ERROR_MARKERS)

    def _execute(self, action: str, args: Dict[str, Any]) -> str:
        result = self.registry.execute(action, args)
        if result is None:
            return "（无输出）"
        if not isinstance(result, str):
            try:
                result = json.dumps(result, ensure_ascii=False)
            except Exception:
                result = str(result)
        return result

    # ── 主循环 ─────────────────────────────────────────────────
    def run(self, task: Task, retries: int = 1) -> bool:
        """执行整个任务，返回是否全部成功。"""
        total = len(task.steps)
        if total == 0:
            return True
        for idx in range(total):
            if idx >= self.max_steps:
                LOG.warning("超过最大步数 %d，中止", self.max_steps)
                task.current_step_idx = idx
                return False

            step = task.steps[idx]
            task.current_step_idx = idx
            step["status"] = "RUNNING"
            self._notify({"task": task, "index": idx, "step": step, "phase": "start"})

            action = str(step.get("action") or step.get("tool") or "")
            args = step.get("args") if isinstance(step.get("args"), dict) else {}

            if not action:
                step["status"] = "OK"
                step["result"] = "（无动作，跳过）"
                task.history.append({"index": idx, "action": "", "ok": True,
                                     "result": step["result"]})
                self._notify({"task": task, "index": idx, "step": step,
                              "phase": "done", "result": step["result"]})
                continue

            ok = False
            last_err = ""
            for attempt in range(retries + 1):
                try:
                    text = self._execute(action, args)
                    if self._is_error(text):
                        last_err = text
                        LOG.warning("步骤 %d 第 %d 次失败: %s", idx, attempt + 1, last_err)
                        continue
                    step["status"] = "OK"
                    step["result"] = text
                    task.history.append({"index": idx, "action": action,
                                         "ok": True, "result": text})
                    self._notify({"task": task, "index": idx, "step": step,
                                  "phase": "done", "result": text})
                    ok = True
                    break
                except Exception as exc:
                    last_err = "%s: %s" % (type(exc).__name__, exc)
                    LOG.warning("步骤 %d 第 %d 次异常: %s", idx, attempt + 1, last_err)

            if not ok:
                step["status"] = "FAILED"
                step["error"] = last_err
                task.history.append({"index": idx, "action": action,
                                     "ok": False, "error": last_err})
                self._notify({"task": task, "index": idx, "step": step,
                              "phase": "failed", "error": last_err})
                return False

        task.current_step_idx = total
        self._notify({"task": task, "index": total, "step": None, "phase": "completed"})
        return True

    def run_plan(self, task: Task, retries: int = 1) -> Dict[str, Any]:
        """执行并返回结构化结果，便于上层（CLI / UI）展示。"""
        ok = self.run(task, retries=retries)
        return {
            "task_id": task.id,
            "goal": task.goal,
            "ok": ok,
            "status": task.status,
            "steps": [
                {"index": i, "desc": s.get("desc"),
                 "action": s.get("action"), "status": s.get("status"),
                 "result": s.get("result"), "error": s.get("error")}
                for i, s in enumerate(task.steps)
            ],
            "history": task.history,
        }
