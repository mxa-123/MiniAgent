# -*- coding: utf-8 -*-
"""Agent 核心：ReAct 循环（思考 → 调工具 → 观察 → 回答）。

两层工具协议：
1. 原生 function calling（优先）；
2. 文本 JSON 块协议（模型不支持 tools 时自动降级，兼容性拉满）。
"""

from __future__ import annotations

import json
import os
import platform
import re
import time
from typing import Any, Callable, Dict, List, Optional

from .llm import LLMError, LLMResponse, ToolCall
from .tools import Registry, Tool
from .util import LOG, now_str, truncate

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.S)

FALLBACK_INSTRUCTION = """\
你可以调用工具。需要调用时，只输出一个 JSON 代码块，不要输出其他内容：
```json
{"tool": "工具名", "arguments": {"参数名": "参数值"}}
```
拿到工具结果后再继续。不需要工具时，直接正常回答。"""


class AgentContext(object):
    """传给插件/工具的运行时上下文。"""

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.cfg = agent.cfg
        self.registry = agent.registry
        self.memory = agent.memory

    def emit(self, kind: str, data: Any = None) -> None:
        self.agent.emit(kind, data)


class Agent(object):
    def __init__(self, cfg, registry: Registry, llm, memory, skills=None, mcp=None):
        self.cfg = cfg
        self.registry = registry
        self.llm = llm
        self.memory = memory
        self.skills = skills          # Skills 对象（可选）
        self.mcp = mcp                # MCPManager（可选）
        self.confirm: Optional[Callable[[Tool, Dict[str, Any]], bool]] = None
        self.on_event: Optional[Callable[[str, Any], None]] = None
        self.max_steps = int(cfg.get("max_steps", 24))
        self.max_output = int(cfg.get("max_tool_output", 8000))
        self.confirm_tools = set(cfg.get("confirm_tools", []) or [])
        self.auto_confirm = bool(cfg.get("auto_confirm", False))
        self.fallback_enabled = bool(cfg.get("fallback_text_protocol", True))
        self.extra_system: List[str] = []

    # ── 事件（CLI / WebUI 都挂这里）──
    def emit(self, kind: str, data: Any = None) -> None:
        if self.on_event:
            try:
                self.on_event(kind, data)
            except Exception as exc:
                LOG.debug("事件回调异常: %s", exc)

    # ── 提示词 ──
    def system_prompt(self) -> str:
        parts = [str(self.cfg.get("system_prompt", "")).strip()]
        parts.append("\n# 运行环境\n- 系统: %s %s\n- 工作目录: %s\n- 当前时间: %s\n- Agent: MiniAgent 0.1"
                     % (platform.system(), platform.release(), os.path.abspath(self.cfg.get("workspace", ".")), now_str()))
        if self.skills:
            catalog = self.skills.catalog()
            if catalog:
                parts.append("\n# 可用技能（需要时用 use_skill 加载详情）\n" + catalog)
        if self.extra_system:
            parts.append("\n" + "\n".join(self.extra_system))
        if self.registry.names():
            parts.append("\n# 可用工具\n" + self.registry.describe())
        return "\n".join(p for p in parts if p).strip()

    def build_messages(self, user_input: str) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt()}]
        for m in self.memory.history():
            role = m.get("role")
            content = m.get("content") or ""
            if role in ("user", "assistant") and content:
                msgs.append({"role": role, "content": content})
        if user_input:
            msgs.append({"role": "user", "content": user_input})
        return msgs

    # ── 主循环 ──
    def chat(self, user_input: str, stream: bool = True) -> str:
        if user_input:
            self.memory.add("user", user_input)
        messages = self.build_messages("")
        tools = self.registry.schemas() or None
        if tools and self.fallback_enabled:
            # 把降级协议说明附加到 system，模型不支持 tools 时才用得上
            messages[0]["content"] += "\n\n" + FALLBACK_INSTRUCTION

        final = ""
        for step in range(1, self.max_steps + 1):
            self.emit("step", {"step": step, "max": self.max_steps})
            try:
                on_delta = (lambda s: self.emit("delta", s)) if stream else None
                resp: LLMResponse = self.llm.chat(messages, tools=tools, stream=stream, on_delta=on_delta)
            except LLMError as exc:
                final = "模型调用失败：%s" % exc
                self.emit("error", final)
                break
            except Exception as exc:
                LOG.exception("模型调用异常")
                final = "模型调用异常：%s: %s" % (type(exc).__name__, exc)
                self.emit("error", final)
                break

            calls = list(resp.tool_calls)
            if not calls and resp.content and self.fallback_enabled and tools:
                calls = self._parse_text_calls(resp.content)

            if not calls:
                final = resp.content or "（模型未返回内容）"
                break

            # 有工具调用时，先记录 assistant 的意图
            messages.append(self._assistant_with_calls(resp, calls))
            for call in calls:
                result = self._run_tool(call)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": result,
                })
            continue
        else:
            final = "（达到最大步数 %d，任务可能未完成）" % self.max_steps

        if final:
            self.memory.add("assistant", final)
        self.emit("final", final)
        return final

    def _assistant_with_calls(self, resp: LLMResponse, calls: List[ToolCall]) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"role": "assistant", "content": resp.content or ""}
        msg["tool_calls"] = [{
            "id": c.id,
            "type": "function",
            "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)},
        } for c in calls]
        return msg

    def _run_tool(self, call: ToolCall) -> str:
        tool = self.registry.get(call.name)
        if tool is None:
            out = "错误：不存在工具 '%s'。可用: %s" % (call.name, ", ".join(self.registry.names()))
            self.emit("tool_result", {"name": call.name, "output": out})
            return out
        self.emit("tool_call", {"name": call.name, "arguments": call.arguments,
                                "risky": tool.risky or call.name in self.confirm_tools})
        need_confirm = (tool.risky or call.name in self.confirm_tools) and not self.auto_confirm
        if need_confirm and self.confirm:
            try:
                if not self.confirm(tool, call.arguments):
                    out = "用户取消了这次调用。"
                    self.emit("tool_result", {"name": call.name, "output": out})
                    return out
            except Exception as exc:
                LOG.warning("确认回调异常: %s", exc)
        started = time.time()
        out = self.registry.execute(call.name, call.arguments, max_output=self.max_output)
        cost = time.time() - started
        self.emit("tool_result", {"name": call.name, "output": out, "seconds": round(cost, 2)})
        return out

    @staticmethod
    def _parse_text_calls(content: str) -> List[ToolCall]:
        """从模型文本里解析 ```json {"tool":..., "arguments":{...}}``` 块。"""
        calls: List[ToolCall] = []
        for block in _JSON_BLOCK_RE.findall(content or ""):
            block = block.strip()
            try:
                data = json.loads(block)
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("tool") or item.get("name") or item.get("tool_name")
                if not name:
                    continue
                args = item.get("arguments") or item.get("args") or item.get("parameters") or {}
                if not isinstance(args, dict):
                    args = {"value": args}
                calls.append(ToolCall(str(name), args))
        return calls
