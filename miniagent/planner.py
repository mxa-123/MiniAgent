# -*- coding: utf-8 -*-
"""Planner：把一句用户需求拆解成结构化的 Task（步骤列表）。

设计思路参考「DeepSeek Harness」公开的规划-执行-反馈分层：
  用户话术 → Planner → Task(goal + steps) → Executor → history → （可选）再规划。

两种规划来源，按优先级：
  1. LLM（可选）：传入带 .chat(messages) 的对象即可，要求返回严格 JSON；
  2. 规则兜底（默认）：无需网络、按关键词映射到已注册工具，Win7 离线也能跑。

仅依赖标准库；语法兼容 Python 3.7（Win7 便携包）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from .kernel import Task

SYSTEM_PROMPT = (
    "你是 AI Agent 的任务规划器。把用户请求拆成可执行的原子步骤。\n"
    "只输出 JSON，不要任何解释文字。格式：\n"
    '{"goal": "总目标", "steps": [{"desc": "这一步做什么", '
    '"action": "工具名", "args": {}}]}\n'
    "要求：\n"
    "1. 每步只做一件事，desc 用中文；\n"
    "2. action 必须来自给定的工具清单；\n"
    "3. args 是该工具的参数对象，缺省写 {}；\n"
    "4. 步骤数不超过 8。"
)

# 关键词 → 工具名（规则兜底用）
_KEYWORD_ACTIONS = [
    (("grep", "搜索文本", "查找内容"), "grep_text"),
    (("搜索文件", "查找文件", "找文件"), "search_files"),
    (("联网", "上网", "网上"), "web_search"),
    (("网页", "抓取", "网址"), "fetch_url"),
    (("读取", "打开文件", "看看文件"), "read_file"),
    (("写入", "保存", "写文件"), "write_file"),
    (("目录", "列出文件"), "list_dir"),
    (("运行", "执行", "命令"), "run_command"),
    (("python", "代码", "脚本"), "python_eval"),
    (("时间", "几点", "日期"), "get_time"),
]

_SPLIT_RE = re.compile(r"[，,。；;、]|\s+然后\s+|\s+再\s+|\s+并且\s+|\s+以及\s+")


class Planner(object):
    """规划器。llm 可选；没有 LLM 时走规则兜底，绝不抛异常。"""

    def __init__(self, llm: Any = None,
                 tool_names: Optional[Sequence[str]] = None,
                 model_name: str = "deepseek-chat",
                 default_action: str = "run_command"):
        self.llm = llm
        self.tool_names = list(tool_names or [])
        self.model_name = model_name
        self.default_action = default_action
        self.last_error = ""

    # ── 对外入口 ───────────────────────────────────────────────
    def plan(self, user_input: str, max_steps: int = 8) -> Task:
        """返回 Task；无论 LLM 是否可用都保证有可执行步骤。"""
        data: Optional[Dict[str, Any]] = None
        if self.llm is not None:
            try:
                data = self._plan_with_llm(user_input, max_steps)
            except Exception as exc:  # LLM 失败不致命，落到规则兜底
                self.last_error = "%s: %s" % (type(exc).__name__, exc)
                data = None
        if data is None:
            data = self._plan_fallback(user_input, max_steps)
        return self._to_task(user_input, data)

    # ── LLM 规划 ───────────────────────────────────────────────
    def _plan_with_llm(self, user_input: str, max_steps: int) -> Optional[Dict[str, Any]]:
        tools = ""
        if self.tool_names:
            tools = "可用工具：\n" + "\n".join("- %s" % t for t in self.tool_names) + "\n\n"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n" + tools},
            {"role": "user", "content": user_input},
        ]
        resp = self.llm.chat(messages)
        content = getattr(resp, "content", None)
        if content is None and isinstance(resp, dict):
            content = resp.get("content")
        if not content:
            return None
        data = _extract_json(content)
        if not data or not isinstance(data.get("steps"), list) or not data["steps"]:
            return None
        for st in data["steps"]:
            if not isinstance(st, dict):
                return None
        data["steps"] = data["steps"][:max_steps]
        return data

    # ── 规则兜底 ───────────────────────────────────────────────
    def _plan_fallback(self, user_input: str, max_steps: int) -> Dict[str, Any]:
        parts = [p.strip() for p in _SPLIT_RE.split(user_input or "") if p and p.strip()]
        if not parts:
            parts = [user_input or "完成任务"]
        steps = []
        for part in parts[:max_steps]:
            action = self._guess_action(part)
            steps.append({
                "desc": part,
                "action": action,
                "args": self._guess_args(action, part),
                "status": "PENDING",
            })
        return {"goal": user_input, "steps": steps}

    def _guess_action(self, text: str) -> str:
        low = text.lower()
        for keys, action in _KEYWORD_ACTIONS:
            for k in keys:
                if k in low:
                    if not self.tool_names or action in self.tool_names:
                        return action
        if self.tool_names and self.default_action in self.tool_names:
            return self.default_action
        return self.tool_names[0] if self.tool_names else self.default_action

    @staticmethod
    def _guess_args(action: str, text: str) -> Dict[str, Any]:
        if action in ("read_file", "write_file", "list_dir"):
            return {"path": text}
        if action in ("search_files", "grep_text"):
            return {"pattern": text}
        if action == "run_command":
            return {"command": text}
        if action == "web_search":
            return {"query": text}
        if action == "fetch_url":
            return {"url": text}
        return {}

    # ── 组装 Task ──────────────────────────────────────────────
    def _to_task(self, user_input: str, data: Dict[str, Any]) -> Task:
        raw_steps = data.get("steps") or []
        steps: List[Dict[str, Any]] = []
        for i, st in enumerate(raw_steps):
            if not isinstance(st, dict):
                continue
            steps.append({
                "desc": str(st.get("desc") or "步骤 %d" % (i + 1)),
                "action": str(st.get("action") or ""),
                "args": st.get("args") if isinstance(st.get("args"), dict) else {},
                "status": "PENDING",
            })
        if not steps:
            steps = [{"desc": user_input or "完成任务", "action": "",
                      "args": {}, "status": "PENDING"}]
        return Task(id="task-%d" % (abs(hash(user_input)) % 100000),
                    goal=str(data.get("goal") or user_input),
                    steps=steps)

    # ── 反馈修正 ───────────────────────────────────────────────
    def update_step(self, task: Task, step_idx: int, result: Any) -> bool:
        """记录一步结果；返回 False 表示需要重新规划。"""
        task.history.append({"index": step_idx, "result": result})
        text = str(result).lower()
        return not ("错误" in text or "异常" in text or "traceback" in text)

    def replan(self, task: Task, user_input: str = "") -> Task:
        """按历史失败原因重新规划（DSH 的自我修正入口）。"""
        hint = user_input or task.goal
        bad = [h for h in task.history if h.get("ok") is False]
        if bad:
            hint = hint + "（上次失败：" + "; ".join(
                str(b.get("error") or b.get("result"))[:120] for b in bad) + "）"
        new = self.plan(hint)
        new.history = list(task.history)
        return new


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从 LLM 输出里抠出第一个完整 JSON 对象（容忍代码块/前后废话）。"""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(cleaned[start:i + 1])
                except Exception:
                    return None
                return obj if isinstance(obj, dict) else None
    return None
