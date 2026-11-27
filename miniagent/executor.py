# -*- coding: utf-8 -*-
"""Executor 模块：驱动 Task 的步骤依次执行，并回填结果。

设计要点（参考 DeepSeek Harness 的「规划-执行-反馈」循环思想，独立实现）：
  1. 每步骤把 step["action"] 交给工具注册表执行，参数取自 step["args"]；
  2. 单步失败时可重试（retries），重试耗尽则标记任务失败并中止；
  3. 每步结果写入 task.history，供 Planner 下次修正；
  4. 可选 on_step 回调，用于把执行进度流式推给界面。

仅依赖标准库；语法兼容 Python 3.7 / 3.8（Win7 便携包）。
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from .kernel import Task
from .util import LOG

# 配置读取（从 config.example.json 或环境变量获取）
DEFAULT_MODEL = "deepseek-chat"
API_BASE = "https://api.deepseek.com/v1"

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

    def _notify(self, payload: Dict[str, Any]) -> None:
        if self.on_step is None:
            return
        try:
            self.on_step(payload)
        except Exception as exc:
            LOG.warning("on_step 回调异常: %s", exc)

    def run(self, task: Task, retries: int = 1) -> bool:
        """执行整个任务，返回是否全部成功。"""
        total = len(task.steps)
        for idx in range(total):
            if idx >= self.max_steps:
                LOG.warning("超过最大步数 %d，中止", self.max_steps)
                return False
            step = task.steps[idx]
            step["status"] = "RUNNING"
            self._notify({"task": task, "index": idx, "step": step, "phase": "start"})

            action = step.get("action") or step.get("tool") or ""
            args = step.get("args") or {}

            ok = False
            last_err = ""
            for attempt in range(retries + 1):
                try:
                    # 调用工具注册表中的方法
                    result = self.registry.execute(action, args)
                    if result is None:
                        result = "（无输出）"
                    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                    
                    # 简单判断错误标识
                    is_err = text.lower().startswith("错误") or "traceback" in text.lower()
                    if is_err:
                        last_err = text
                        LOG.warning("步骤 %d 第 %d 次失败: %s", idx, attempt + 1, last_err)
                        continue
                    step["status"] = "OK"
                    step["result"] = text
                    task.update_history({"index": idx, "action": action,
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
                task.update_history({"index": idx, "action": action,
                                    "ok": False, "error": last_err})
                self._notify({"task": task, "index": idx, "step": step,
                              "phase": "failed", "error": last_err})
                return False

        # 全部完成
        task.current_step_idx = total
        task.steps[total-1]["status"] = "COMPLETED"
        self._notify({"task": task, "index": total, "step": None,
                       "phase": "completed"})
        return ok

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

if __name__ == "__main__":
    # 此处仅供手动测试运行
    import sys
    from miniagent.kernel import Kernel
    from miniagent.planner import Planner
    from miniagent.tools import Registry
    
    k = Kernel()
    reg = Registry()
    # 注册一个简单的 mock 工具用于测试
    reg.register(name="inspect_files", description="检查文件", action="mock_check")
    
    p = Planner()
    t = p.plan("帮我把这些图片处理了并更新到 GitHub")
    e = Executor(registry=reg)
    e.run_plan(t)
    print(f"Final Result: {t.status}")
    print(f"History: {t.history}")

import sys
if __name__ == "__main__":
    # 此处仅供手动测试运行
    pass
