# -*- coding: utf-8 -*-
"""WebUI 冒烟：起本地服务，验证首页、状态接口与 SSE 对话流。

运行： python tests/check_webui.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from miniagent.config import Config  # noqa: E402
from miniagent.runtime import Runtime  # noqa: E402
from miniagent.webui import serve  # noqa: E402

PORT = 8799


def main():
    cfg = Config({"provider": "mock", "workspace": ".", "stream": False,
                  "mcpServers": {}, "plugins_dir": "plugins", "skills_dir": "skills"})
    rt = Runtime(cfg, home=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_webui"))
    rt.build()
    t = threading.Thread(target=serve, args=(rt,), kwargs={"host": "127.0.0.1", "port": PORT,
                                                           "open_browser": False}, daemon=True)
    t.start()
    time.sleep(1.2)
    base = "http://127.0.0.1:%d" % PORT
    ok = True

    try:
        status = json.loads(urllib.request.urlopen(base + "/api/status", timeout=8).read().decode("utf-8"))
        print("status:", status)
        ok = ok and status.get("tools", 0) > 0

        html = urllib.request.urlopen(base + "/", timeout=8).read().decode("utf-8")
        print("index html bytes:", len(html))
        ok = ok and ("MiniAgent" in html)

        tools = json.loads(urllib.request.urlopen(base + "/api/tools", timeout=8).read().decode("utf-8"))
        print("tools via api:", len(tools))
        ok = ok and len(tools) > 0

        resp = urllib.request.urlopen(base + "/api/chat?q=" +
                                      urllib.request.quote("你好"), timeout=30)
        chunks = []
        started = time.time()
        for raw in resp:
            chunks.append(raw.decode("utf-8", "replace"))
            if time.time() - started > 20:
                break
        sse = "".join(chunks)
        print("sse events:", sse.count("data:"), "| done:", "done" in sse)
        ok = ok and ("done" in sse)
    except Exception as exc:
        print("FAIL:", type(exc).__name__, exc)
        ok = False

    print("WebUI 检查:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
