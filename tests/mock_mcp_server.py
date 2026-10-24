# -*- coding: utf-8 -*-
"""一个假的 MCP 服务器（stdio / JSON-RPC），用于测试 MiniAgent 的 MCP 客户端。

运行方式：由 MCPManager 以子进程启动，不要手动跑。
"""

import json
import sys


def reply(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


TOOLS = [{
    "name": "echo",
    "description": "把输入原样返回（测试用）",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "要回显的文本"}},
        "required": ["text"],
    },
}]


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = req.get("method")
        rid = req.get("id")
        if rid is None:
            continue  # 通知类消息不回
        if method == "initialize":
            reply({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock", "version": "1.0"}}})
        elif method == "tools/list":
            reply({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            args = (req.get("params") or {}).get("arguments") or {}
            reply({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": "echo: " + str(args.get("text", ""))}],
                "isError": False}})
        else:
            reply({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "未知方法 " + str(method)}})


if __name__ == "__main__":
    main()
