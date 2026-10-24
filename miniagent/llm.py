# -*- coding: utf-8 -*-
"""LLM 适配层：统一消息格式 + 三种后端（OpenAI 兼容 / Ollama 原生 / Mock）。

只用标准库 urllib，Win7 上不需要额外 DLL。
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .util import LOG, truncate


class ToolCall(object):
    def __init__(self, name: str, arguments: Dict[str, Any], call_id: Optional[str] = None):
        self.name = name
        self.arguments = arguments or {}
        self.id = call_id or ("call_%s" % id(self))

    def __repr__(self) -> str:  # pragma: no cover
        return "<ToolCall %s %s>" % (self.name, truncate(self.arguments, 80))


class LLMResponse(object):
    def __init__(self, content: str = "", tool_calls: Optional[List[ToolCall]] = None,
                 raw: Any = None, finish_reason: str = ""):
        self.content = content or ""
        self.tool_calls = tool_calls or []
        self.raw = raw
        self.finish_reason = finish_reason

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMError(Exception):
    pass


class BaseLLM(object):
    name = "base"

    def __init__(self, cfg):
        self.cfg = cfg
        self.model = cfg.get("model")
        self.timeout = int(cfg.get("timeout", 120))

    # 子类实现
    def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None,
             stream: bool = False, on_delta: Optional[Callable[[str], None]] = None) -> LLMResponse:
        raise NotImplementedError

    def list_models(self) -> List[str]:
        return []

    # ── 公共 HTTP ──
    def _post_json(self, url: str, payload: Dict[str, Any], headers: Dict[str, str],
                   stream: bool = False):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        ctx = ssl.create_default_context()
        try:
            ctx.check_hostname = True
        except Exception:
            pass
        try:
            return urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:
                pass
            raise LLMError("HTTP %s: %s" % (exc.code, truncate(body, 500)))
        except urllib.error.URLError as exc:
            raise LLMError("网络错误: %s（URL=%s）" % (exc.reason, url))


class OpenAICompatLLM(BaseLLM):
    """DeepSeek / OpenAI / Moonshot / 智谱 / vLLM / Ollama 的 OpenAI 端点，通吃。"""

    name = "openai_compat"

    def __init__(self, cfg):
        BaseLLM.__init__(self, cfg)
        base = str(cfg.get("api_base", "")).rstrip("/")
        # 允许只填域名，自动补 /v1
        if base and not base.endswith("/v1") and "/v1" not in base:
            base = base + "/v1"
        self.base = base
        self.api_key = cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", "")

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        return h

    def chat(self, messages, tools=None, stream=False, on_delta=None) -> LLMResponse:
        if not self.base:
            raise LLMError("未配置 api_base")
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": float(self.cfg.get("temperature", 0.3)),
            "stream": bool(stream),
        }
        mt = self.cfg.get("max_tokens")
        if mt:
            payload["max_tokens"] = int(mt)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        url = self.base + "/chat/completions"
        if stream:
            return self._stream(url, payload, on_delta)
        resp = self._post_json(url, payload, self._headers())
        body = json.loads(resp.read().decode("utf-8", "replace"))
        return self._parse(body)

    def _stream(self, url: str, payload: Dict[str, Any], on_delta) -> LLMResponse:
        resp = self._post_json(url, payload, self._headers(), stream=True)
        content_parts: List[str] = []
        calls: Dict[int, Dict[str, Any]] = {}
        finish = ""
        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except Exception:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                finish = choices[0].get("finish_reason") or finish
                piece = delta.get("content")
                if piece:
                    content_parts.append(piece)
                    if on_delta:
                        on_delta(piece)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = calls.setdefault(idx, {"id": None, "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]
        finally:
            try:
                resp.close()
            except Exception:
                pass
        tool_calls = []
        for idx in sorted(calls.keys()):
            slot = calls[idx]
            try:
                args = json.loads(slot["args"]) if slot["args"].strip() else {}
            except Exception:
                args = {"_raw": slot["args"]}
            if slot["name"]:
                tool_calls.append(ToolCall(slot["name"], args, slot["id"]))
        return LLMResponse("".join(content_parts), tool_calls, finish_reason=finish)

    @staticmethod
    def _parse(body: Dict[str, Any]) -> LLMResponse:
        choices = body.get("choices") or []
        if not choices:
            raise LLMError("响应中没有 choices: %s" % truncate(body, 300))
        msg = choices[0].get("message") or {}
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                args = {"_raw": raw_args}
            calls.append(ToolCall(fn.get("name", ""), args, tc.get("id")))
        return LLMResponse(msg.get("content") or "", calls, raw=body,
                           finish_reason=choices[0].get("finish_reason", ""))

    def list_models(self) -> List[str]:
        try:
            req = urllib.request.Request(self.base + "/models", headers=self._headers())
            with urllib.request.urlopen(req, timeout=min(self.timeout, 20)) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
            return [m.get("id", "") for m in body.get("data", [])]
        except Exception as exc:
            LOG.warning("拉取模型列表失败: %s", exc)
            return []


class OllamaLLM(BaseLLM):
    """Ollama 原生 /api/chat（支持 tools 的 qwen / llama3 系列）。"""

    name = "ollama"

    def __init__(self, cfg):
        BaseLLM.__init__(self, cfg)
        base = str(cfg.get("api_base") or "http://127.0.0.1:11434")
        self.base = base.replace("/v1", "").rstrip("/")

    def chat(self, messages, tools=None, stream=False, on_delta=None) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": bool(stream),
            "options": {"temperature": float(self.cfg.get("temperature", 0.3))},
        }
        if tools:
            payload["tools"] = [_to_ollama_tool(t) for t in tools]
        url = self.base + "/api/chat"
        if stream:
            return self._stream(url, payload, on_delta)
        resp = self._post_json(url, payload, {"Content-Type": "application/json"})
        body = json.loads(resp.read().decode("utf-8", "replace"))
        return self._parse(body)

    def _stream(self, url, payload, on_delta) -> LLMResponse:
        resp = self._post_json(url, payload, {"Content-Type": "application/json"}, stream=True)
        parts: List[str] = []
        calls: List[ToolCall] = []
        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                msg = chunk.get("message") or {}
                piece = msg.get("content")
                if piece:
                    parts.append(piece)
                    if on_delta:
                        on_delta(piece)
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args or "{}")
                        except Exception:
                            args = {"_raw": args}
                    calls.append(ToolCall(fn.get("name", ""), args or {}))
                if chunk.get("done"):
                    break
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return LLMResponse("".join(parts), calls, finish_reason="stop")

    @staticmethod
    def _parse(body: Dict[str, Any]) -> LLMResponse:
        msg = body.get("message") or {}
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except Exception:
                    args = {"_raw": args}
            calls.append(ToolCall(fn.get("name", ""), args or {}))
        return LLMResponse(msg.get("content") or "", calls, raw=body)

    def list_models(self) -> List[str]:
        try:
            with urllib.request.urlopen(self.base + "/api/tags", timeout=min(self.timeout, 20)) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
            return [m.get("name", "") for m in body.get("models", [])]
        except Exception as exc:
            LOG.warning("Ollama 拉取模型失败: %s", exc)
            return []


def _to_ollama_tool(t: Dict[str, Any]) -> Dict[str, Any]:
    fn = t.get("function") if t.get("type") == "function" else t
    return {"type": "function", "function": fn}


class MockLLM(BaseLLM):
    """离线后端：按脚本队列返回，用于冒烟测试与无网络演示。"""

    name = "mock"

    def __init__(self, cfg, script=None):
        BaseLLM.__init__(self, cfg)
        self.script: List[LLMResponse] = list(script or [])
        self.seen_messages: List[Dict[str, Any]] = []

    def chat(self, messages, tools=None, stream=False, on_delta=None) -> LLMResponse:
        self.seen_messages = list(messages)
        if self.script:
            resp = self.script.pop(0)
        else:
            resp = self._demo_reply(messages)
        if stream and on_delta and resp.content:
            for i in range(0, len(resp.content), 12):
                on_delta(resp.content[i:i + 12])
        return resp

    def _demo_reply(self, messages) -> LLMResponse:
        """无脚本时的内置演示：按对话进度返回固定的两步工具调用 + 总结。

        让未配置模型的用户（含线上试玩版）也能体验完整的工具调用流程。
        """
        q = ""
        for m in messages:
            if m.get("role") == "user":
                q = str(m.get("content", ""))
        done_tools = sum(1 for m in messages if m.get("role") == "tool")
        if "时间" in q or "日期" in q or "几点" in q:
            if done_tools == 0:
                return LLMResponse("好的，我查一下当前时间。",
                                   tool_calls=[ToolCall("get_time", {}, "demo_t1")])
            return LLMResponse("以上就是当前时间（离线演示后端）。"
                               "完整功能请下载 Windows 安装包，配置任意 OpenAI 兼容模型即可使用。")
        m = re.search(u"[「\\\"']([^」\\\"']+)[」\\\"']", q)
        payload = m.group(1) if m else "MiniAgent 演示"
        fm = re.search(u"[A-Za-z0-9_\\-]+\\.(?:txt|md|json|py|csv)", q)
        fname = fm.group(0) if fm else "demo.txt"
        if done_tools == 0:
            return LLMResponse("好的，我用 write_file 把内容写入文件。",
                               tool_calls=[ToolCall("write_file",
                                                    {"path": fname, "content": payload},
                                                    "demo_1")])
        if done_tools == 1:
            return LLMResponse("已写入，再用 read_file 读回来核对。",
                               tool_calls=[ToolCall("read_file", {"path": fname}, "demo_2")])
        return LLMResponse(u"完成！已把「%s」写入 %s 并读回确认，内容一致。"
                           u"\n（当前是离线演示后端；完整功能请下载 Windows 安装包，"
                           u"配置任意 OpenAI 兼容 / Ollama 模型即可使用。）" % (payload, fname))


def create_llm(cfg, script=None):
    provider = str(cfg.get("provider", "openai_compat")).lower()
    if provider in ("openai_compat", "openai", "deepseek", "compat"):
        return OpenAICompatLLM(cfg)
    if provider in ("ollama", "ollama_native"):
        return OllamaLLM(cfg)
    if provider == "mock":
        return MockLLM(cfg, script=script)
    raise LLMError("未知 provider: %s（可选 openai_compat / ollama / mock）" % provider)
