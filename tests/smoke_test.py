# -*- coding: utf-8 -*-
"""冒烟测试：不联网、不需要 API Key，用 Mock 后端跑通全链路。

运行： python tests/smoke_test.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from miniagent.agent import Agent  # noqa: E402
from miniagent.config import Config  # noqa: E402
from miniagent.llm import LLMResponse, MockLLM, ToolCall  # noqa: E402
from miniagent.memory import Memory  # noqa: E402
from miniagent.plugins import PluginManager  # noqa: E402
from miniagent.runtime import Runtime  # noqa: E402
from miniagent.skills import parse_skill  # noqa: E402
from miniagent.tools import Registry  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("%s  %s%s" % ("PASS" if cond else "FAIL", name, ("  → " + str(extra)) if extra else ""))


def main():
    tmp = tempfile.mkdtemp(prefix="miniagent_test_")
    home = os.path.join(tmp, "home")
    ws = os.path.join(tmp, "work")
    os.makedirs(ws, exist_ok=True)

    cfg = Config({
        "provider": "mock",
        "workspace": ws,
        "auto_confirm": True,
        "stream": False,
        "confirm_tools": [],
        "skills_dir": os.path.join(tmp, "skills"),
        "plugins_dir": os.path.join(tmp, "plugins"),
        "enable_builtin_tools": True,
        "mcpServers": {},
    })

    # 1. 运行时装配
    rt = Runtime(cfg, home=home)
    rt.build()
    names = rt.registry.names()
    check("内置工具注册", len(names) >= 10, "%d 个: %s" % (len(names), ",".join(names[:6])))
    check("工具 schema 生成", "path" in rt.registry.get("read_file").parameters.get("properties", {}))

    # 2. 文件工具闭环
    r = rt.registry
    r.execute("write_file", {"path": "demo/hello.txt", "content": "第一行\n第二行 hello world\n"})
    out = r.execute("read_file", {"path": "demo/hello.txt"})
    check("write_file + read_file", "hello world" in out, out[:40])
    check("list_dir", "demo" in r.execute("list_dir", {"path": "."}))
    check("search_files", "demo/hello.txt" in r.execute("search_files", {"pattern": "**/*.txt"}))
    check("grep_text", "hello" in r.execute("grep_text", {"pattern": "hello", "path": "."}))
    check("越权路径被拦截", "拒绝" in r.execute("read_file", {"path": "../outside.txt"}))

    # 3. python_eval 子进程
    out = r.execute("python_eval", {"code": "print(6*7)"})
    check("python_eval", "42" in out, out[:60])

    # 4. run_command
    out = r.execute("run_command", {"command": "python -c \"print('ok')\"" if os.name != "nt" else "echo ok"})
    check("run_command", "ok" in out.lower(), out[:60])

    # 5. 记忆
    mem = Memory(home)
    mem.remember("测试记忆：项目代号 灵枢", tag="test")
    check("长期记忆写入与检索", "灵枢" in mem.recall("灵枢"))
    mem.add("user", "你好")
    check("会话历史", len(mem.history()) == 1)

    # 6. 技能解析
    skill = parse_skill(u"---\nname: 测试技能\ndescription: 用于测试\n---\n步骤一：做A\n步骤二：做B\n")
    check("技能 frontmatter 解析", skill.name == u"测试技能" and u"步骤一" in skill.body, skill.name)

    # 7. 插件加载（用仓库自带示例插件）
    plugins_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
    pm = PluginManager(plugins_dir, Registry(), rt.ctx)
    pm.registry = Registry()  # 用独立工具表，验证 @tool 与 setup 两种注册方式
    pm.ctx.registry = pm.registry
    loaded = pm.load_all()
    ok = [p for p in loaded if p.ok]
    tools = set(ok[0].tools) if ok else set()
    check("示例插件加载（@tool + setup）", len(ok) >= 1 and {"calc", "system_info", "dir_stats"} <= tools,
          sorted(tools))

    # 8. Agent 循环（原生 function calling）
    rt2 = Runtime(Config({
        "provider": "mock", "workspace": ws, "auto_confirm": True, "stream": False,
        "skills_dir": "", "plugins_dir": "", "mcpServers": {},
    }), home=home)
    script = [
        LLMResponse("", [ToolCall("write_file", {"path": "agent.txt", "content": "由 Agent 写入"})]),
        LLMResponse("", [ToolCall("read_file", {"path": "agent.txt"})]),
        LLMResponse(u"已确认写入内容。"),
    ]
    rt2.llm = MockLLM(rt2.cfg, script=script)
    rt2.build()
    answer = rt2.agent.chat(u"写个文件再读回来")
    check("Agent 多步工具循环", u"已确认" in answer and os.path.isfile(os.path.join(ws, "agent.txt")), answer[:60])

    # 9. 文本降级协议
    calls = Agent._parse_text_calls(u"好的\n```json\n{\"tool\": \"get_time\", \"arguments\": {}}\n```")
    check("文本 JSON 工具块解析", len(calls) == 1 and calls[0].name == "get_time")

    # 10. MCP 客户端（连一个本地假服务器）
    from miniagent.mcp import MCPManager
    here = os.path.dirname(os.path.abspath(__file__))
    mgr = MCPManager({"mock": {"command": sys.executable,
                               "args": [os.path.join(here, "mock_mcp_server.py")],
                               "enabled": True, "timeout": 10}})
    reg = Registry()
    got = mgr.connect_all(reg)
    tool_name = "mcp__mock__echo"
    check("MCP 连接并注册工具", tool_name in reg.names(), got)
    out = reg.execute(tool_name, {"text": u"你好MCP"}) if tool_name in reg.names() else ""
    check("MCP 工具调用", u"你好MCP" in out, out[:60])
    mgr.shutdown()

    # 11. 流式接口（Mock 分流）
    deltas = []
    mock = MockLLM(rt2.cfg, script=[LLMResponse(u"流式内容测试")])
    resp = mock.chat([{"role": "user", "content": "x"}], stream=True, on_delta=deltas.append)
    check("流式分发", "".join(deltas) == resp.content == u"流式内容测试")

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d 项通过, %d 项失败" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  FAIL: " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
