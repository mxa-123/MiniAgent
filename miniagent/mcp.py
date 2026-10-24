# -*- coding: utf-8 -*-
"""MCP 客户端（stdio / JSON-RPC 2.0，纯标准库实现）。

配置示例（config.json）：
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "E:/work"],
        "enabled": true
      }
    }
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from .tools import Tool
from .util import LOG

PROTOCOL_VERSION = "2024-11-05"


class MCPError(Exception):
    pass


class MCPServer(object):
    """一个 stdio 方式的 MCP 服务器进程。"""

    def __init__(self, name: str, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None,
                 timeout: float = 30.0):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = env or {}
        self.cwd = cwd
        self.timeout = timeout
        self.proc: Optional[subprocess.Popen] = None
        self._q: "queue.Queue" = queue.Queue()
        self._id = 0
        self._lock = threading.Lock()
        self.server_info: Dict[str, Any] = {}
        self.tools: List[Dict[str, Any]] = []

    # ── 生命周期 ──
    def start(self) -> None:
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in self.env.items()})
        env.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            self.proc = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=env, cwd=self.cwd or None,
                startupinfo=_no_window(),
            )
        except FileNotFoundError:
            raise MCPError("找不到命令: %s（MCP 服务器 %s）" % (self.command, self.name))
        except Exception as exc:
            raise MCPError("启动 %s 失败: %s" % (self.name, exc))
        t = threading.Thread(target=self._reader, name="mcp-reader-" + self.name, daemon=True)
        t.start()
        self._initialize()

    def _initialize(self) -> None:
        resp = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "miniagent", "version": "0.1.0"},
        })
        self.server_info = resp.get("result") or {}
        try:
            self.notify("notifications/initialized", {})
        except Exception:
            pass
        try:
            listed = self.request("tools/list", {})
            self.tools = (listed.get("result") or {}).get("tools") or []
        except Exception as exc:
            LOG.warning("MCP %s 拉取工具列表失败: %s", self.name, exc)
            self.tools = []

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # ── 协议 ──
    def _reader(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    LOG.debug("MCP %s 非 JSON 输出: %s", self.name, line[:200])
                    continue
                self._q.put(msg)
        except Exception as exc:
            LOG.debug("MCP %s 读取线程结束: %s", self.name, exc)

    def _send(self, payload: Dict[str, Any]) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def request(self, method: str, params: Optional[Dict[str, Any]] = None,
                timeout: Optional[float] = None) -> Dict[str, Any]:
        if self.proc is None:
            raise MCPError("MCP 服务器 %s 未启动" % self.name)
        with self._lock:
            self._id += 1
            req_id = self._id
            self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
            deadline = time.time() + (timeout or self.timeout)
            while time.time() < deadline:
                try:
                    msg = self._q.get(timeout=0.4)
                except queue.Empty:
                    if self.proc.poll() is not None:
                        raise MCPError("MCP 服务器 %s 已退出（退出码 %s）" % (self.name, self.proc.returncode))
                    continue
                if msg.get("id") == req_id:
                    if "error" in msg:
                        err = msg["error"]
                        raise MCPError("%s: %s" % (err.get("code"), err.get("message")))
                    return msg
                # 其他 id 的消息是通知/乱序响应，丢弃
            raise MCPError("MCP 请求超时: %s（%s 秒）" % (method, timeout or self.timeout))

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        if self.proc is None:
            return
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        resp = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        result = resp.get("result") or {}
        parts: List[str] = []
        for item in result.get("content") or []:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
        if parts:
            return "\n".join(parts)
        if result.get("isError"):
            return "MCP 工具报错：%s" % json.dumps(result, ensure_ascii=False)[:2000]
        return json.dumps(result, ensure_ascii=False)[:4000]


def _no_window():
    """Windows 下隐藏子进程控制台窗口（Win7 也支持）。"""
    try:
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            return si
    except Exception:
        pass
    return None


class MCPManager(object):
    def __init__(self, servers_cfg: Optional[Dict[str, Any]] = None):
        self.cfg = servers_cfg or {}
        self.servers: Dict[str, MCPServer] = {}
        self.errors: Dict[str, str] = {}

    def connect_all(self, registry, source: str = "mcp") -> Dict[str, List[str]]:
        """启动所有 enabled 的服务器并把它们的工具注册进 registry。"""
        registered: Dict[str, List[str]] = {}
        for name, conf in (self.cfg or {}).items():
            if not isinstance(conf, dict) or not conf.get("enabled", True):
                continue
            try:
                srv = MCPServer(
                    name=str(name),
                    command=str(conf.get("command", "")),
                    args=conf.get("args") or [],
                    env=conf.get("env"),
                    cwd=conf.get("cwd"),
                    timeout=float(conf.get("timeout", 30)),
                )
                srv.start()
                self.servers[str(name)] = srv
                names: List[str] = []
                for t in srv.tools:
                    tool_name = _safe_name("mcp__%s__%s" % (name, t.get("name", "")))
                    schema = t.get("inputSchema") or {"type": "object", "properties": {}}
                    registry.register(Tool(
                        name=tool_name,
                        description=(t.get("description") or ("MCP %s 的 %s" % (name, t.get("name"))))[:1000],
                        parameters=schema,
                        func=_make_caller(srv, t.get("name", "")),
                        risky=False,
                        source="mcp:" + str(name),
                    ))
                    names.append(tool_name)
                registered[str(name)] = names
                LOG.info("MCP %s 已连接，工具 %d 个", name, len(names))
            except Exception as exc:
                self.errors[str(name)] = str(exc)
                LOG.warning("MCP %s 连接失败: %s", name, exc)
        return registered

    def shutdown(self) -> None:
        for srv in self.servers.values():
            try:
                srv.stop()
            except Exception:
                pass
        self.servers = {}

    def summary(self) -> str:
        if not self.servers and not self.errors:
            return "（未配置 MCP 服务器）"
        lines = []
        for name, srv in self.servers.items():
            lines.append("- %s [%s] 工具 %d 个" % (name, "运行中" if srv.running else "已停止", len(srv.tools)))
        for name, err in self.errors.items():
            lines.append("- %s [失败] %s" % (name, err))
        return "\n".join(lines)


def _make_caller(srv: MCPServer, tool_name: str):
    def caller(**kwargs):
        return srv.call_tool(tool_name, kwargs)
    caller.__name__ = "mcp_" + re.sub(r"\W", "_", tool_name)
    caller.__doc__ = "调用 MCP 工具 %s（来自 %s）" % (tool_name, srv.name)
    return caller


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    return safe[:64]
