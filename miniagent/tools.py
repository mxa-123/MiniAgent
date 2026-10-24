# -*- coding: utf-8 -*-
"""工具注册表：从 Python 函数自动生成 OpenAI function-calling JSON Schema。"""

from __future__ import annotations

import inspect
import json
import re
import typing
from typing import Any, Callable, Dict, List, Optional

from .util import LOG, truncate

_PARAM_RE = re.compile(r"^\s*(?::param\s+(?P<n1>\w+)\s*:|(?P<n2>\w+)\s*(?:\([^)]*\))?\s*:)\s*(?P<desc>.+)$")

_TYPE_MAP = {
    "str": "string",
    "string": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "Any": "string",
}


class ToolError(Exception):
    """工具执行失败（预期内错误，消息直接回给模型）。"""


class Tool(object):
    """一个可调用工具的定义。"""

    def __init__(self, name: str, description: str, parameters: Dict[str, Any],
                 func: Callable[..., Any], risky: bool = False, source: str = "builtin"):
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}, "required": []}
        self.func = func
        self.risky = risky
        self.source = source

    def schema(self) -> Dict[str, Any]:
        """OpenAI tools 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def ollama_schema(self) -> Dict[str, Any]:
        """Ollama 原生 tools 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def invoke(self, arguments: Dict[str, Any]) -> Any:
        if not isinstance(arguments, dict):
            raise ToolError("参数必须是 JSON 对象，实际: %r" % (arguments,))
        return self.func(**arguments)

    def __repr__(self) -> str:  # pragma: no cover
        return "<Tool %s (%s)>" % (self.name, self.source)


class Registry(object):
    """工具注册中心，支持分组与运行时增删。"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool, override: bool = True) -> Tool:
        if tool.name in self._tools and not override:
            raise ToolError("工具名冲突: %s" % tool.name)
        if tool.name in self._tools:
            LOG.debug("工具 %s 被覆盖（来源 %s）", tool.name, tool.source)
        self._tools[tool.name] = tool
        return tool

    def register_func(self, func: Callable[..., Any], name: Optional[str] = None,
                      description: Optional[str] = None, risky: bool = False,
                      source: str = "plugin") -> Tool:
        meta = getattr(func, "_tool_meta", None) or {}
        return self.register(tool_from_function(
            func,
            name=name or meta.get("name"),
            description=description or meta.get("description"),
            risky=risky or bool(meta.get("risky", False)),
            source=source,
        ))

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return sorted(self._tools.keys())

    def all(self) -> List[Tool]:
        return [self._tools[n] for n in self.names()]

    def schemas(self) -> List[Dict[str, Any]]:
        return [t.schema() for t in self.all()]

    def describe(self) -> str:
        lines = []
        for t in self.all():
            req = ",".join(t.parameters.get("required", [])) or "-"
            lines.append("- %s(%s) [%s] %s" % (t.name, req, t.source, t.description.split("\n")[0]))
        return "\n".join(lines)

    def execute(self, name: str, arguments: Dict[str, Any], max_output: int = 8000) -> str:
        tool = self.get(name)
        if tool is None:
            return "错误：不存在工具 '%s'。可用工具: %s" % (name, ", ".join(self.names()))
        try:
            result = tool.invoke(arguments)
            if result is None:
                result = "（无输出）"
            if not isinstance(result, str):
                try:
                    result = json.dumps(result, ensure_ascii=False, indent=2)
                except Exception:
                    result = str(result)
        except ToolError as exc:
            return "错误：%s" % exc
        except TypeError as exc:
            return "错误：参数不匹配(%s)。该工具签名: %s" % (exc, _signature_hint(tool))
        except Exception as exc:
            LOG.exception("工具 %s 执行异常", name)
            return "异常：%s: %s" % (type(exc).__name__, exc)
        return truncate(result, max_output)


def _signature_hint(tool: Tool) -> str:
    props = tool.parameters.get("properties", {})
    return "%s(%s)" % (tool.name, ", ".join(sorted(props.keys())))


def _json_type(annotation: Any) -> str:
    try:
        origin = typing.get_origin(annotation)
    except Exception:
        origin = getattr(annotation, "__origin__", None)
    if origin is typing.Union:
        args = typing.get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        return _json_type(non_none[0]) if non_none else "string"
    if origin in (list, set, tuple):
        return "array"
    if origin is dict:
        return "object"
    name = getattr(annotation, "__name__", None) or str(annotation)
    return _TYPE_MAP.get(str(name).lower(), "string")


def _doc_param_desc(doc: str) -> Dict[str, str]:
    """支持 `:param x: 描述` 与 Google 风格 `x: 描述`。"""
    out: Dict[str, str] = {}
    if not doc:
        return out
    in_args = False
    for raw in doc.splitlines():
        line = raw.rstrip()
        if re.match(r"^\s*(Args|参数)\s*:\s*$", line):
            in_args = True
            continue
        if in_args:
            if not line.strip():
                in_args = False
                continue
            if re.match(r"^\s*(Returns|返回|Raises|Example|示例)\s*:", line):
                in_args = False
                continue
        m = _PARAM_RE.match(line)
        if m:
            key = m.group("n1") or m.group("n2")
            desc = m.group("desc").strip()
            if key and desc and ":param" not in desc:
                out[key] = desc
    return out


def _split_doc(doc: str):
    doc = (doc or "").strip()
    if not doc:
        return "", {}
    lines = doc.splitlines()
    summary = lines[0].strip()
    return summary, _doc_param_desc(doc)


def tool_from_function(func: Callable[..., Any], name: Optional[str] = None,
                       description: Optional[str] = None, risky: bool = False,
                       source: str = "builtin") -> Tool:
    sig = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = getattr(func, "__annotations__", {}) or {}
    summary, param_desc = _split_doc(inspect.getdoc(func) or "")
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        ann = hints.get(pname, str)
        entry: Dict[str, Any] = {"type": _json_type(ann), "description": param_desc.get(pname, "")}
        if isinstance(ann, str):  # from __future__ import annotations 未解析成功时的兜底
            entry["type"] = _TYPE_MAP.get(ann.lower().replace("optional[", "").rstrip("]"), "string")
        properties[pname] = entry
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    schema = {"type": "object", "properties": properties, "required": required}
    return Tool(
        name=name or getattr(func, "__name__", "anonymous"),
        description=description or summary or (name or "工具"),
        parameters=schema,
        func=func,
        risky=risky or bool(getattr(func, "_risky", False)),
        source=source,
    )


def tool(name: Optional[str] = None, description: Optional[str] = None, risky: bool = False):
    """装饰器：把函数变成工具定义（延迟到注册时才生成 schema）。"""

    def deco(func: Callable[..., Any]) -> Callable[..., Any]:
        func._tool_meta = {  # type: ignore[attr-defined]
            "name": name or func.__name__,
            "description": description,
            "risky": risky,
        }
        return func

    return deco


def collect_from_module(module: Any, source: str = "plugin") -> List[Tool]:
    """扫描模块里带 _tool_meta 的函数。"""
    found: List[Tool] = []
    for _, obj in inspect.getmembers(module, callable):
        meta = getattr(obj, "_tool_meta", None)
        if not meta:
            continue
        found.append(tool_from_function(obj, name=meta.get("name"), description=meta.get("description"),
                                        risky=meta.get("risky", False), source=source))
    return found
