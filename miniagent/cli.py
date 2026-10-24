# -*- coding: utf-8 -*-
"""命令行界面：REPL + 斜杠命令。兼容 Windows 7 的 cmd.exe（不使用 ANSI 颜色）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .config import DEFAULT_HOME, Config
from .runtime import Runtime
from .tools import Tool
from .util import LOG, setup_console, setup_logging, short, truncate

BANNER = """\
MiniAgent %s —— Win7/8.1 可用的可扩展 AI Agent
输入 /help 查看命令，/exit 退出。"""

HELP = """\
命令：
  /help              显示本帮助
  /status            查看模型 / 工具 / 插件 / MCP 状态
  /tools [关键词]    列出工具，可带筛选
  /skills            列出技能
  /plugins           列出插件（含加载错误）
  /mcp               列出 MCP 服务器
  /model <名称>      切换模型
  /config [k] [v]    查看或临时修改配置（如 /config temperature 0.7）
  /new               清空当前会话
  /save [文件]       导出会话到 JSONL
  /sessions          列出历史会话
  /load <会话文件>   载入历史会话
  /reload            热重载插件与技能
  /confirm on|off    开关危险工具确认
  /exit              退出
"""

EXIT_WORDS = ("/exit", "/quit", "exit", "quit", "退出")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="miniagent", description="MiniAgent —— 轻量可扩展 AI Agent")
    p.add_argument("-c", "--config", help="配置文件路径")
    p.add_argument("-p", "--prompt", help="一次性提问后退出")
    p.add_argument("-w", "--workspace", help="工作目录（工具作用的根目录）")
    p.add_argument("--home", help="数据目录（会话/记忆），默认 ~/.miniagent")
    p.add_argument("--model", help="覆盖模型名")
    p.add_argument("--provider", help="openai_compat / ollama / mock")
    p.add_argument("--api-base", dest="api_base", help="覆盖 API 地址")
    p.add_argument("--api-key", dest="api_key", help="覆盖 API Key")
    p.add_argument("--session", help="会话名（用于断点续聊）")
    p.add_argument("--no-stream", action="store_true", help="关闭流式输出")
    p.add_argument("--web", action="store_true", help="启动本地 Web 界面")
    p.add_argument("--port", type=int, help="Web 界面端口")
    p.add_argument("--list-tools", action="store_true", help="打印工具清单后退出")
    p.add_argument("--init", action="store_true", help="生成默认配置文件后退出")
    p.add_argument("--log-level", dest="log_level", help="DEBUG/INFO/WARNING")
    p.add_argument("-v", "--version", action="store_true", help="显示版本")
    return p


def apply_cli_overrides(cfg: Config, args: argparse.Namespace) -> None:
    if getattr(args, "model", None):
        cfg.set("model", args.model)
    if getattr(args, "provider", None):
        cfg.set("provider", args.provider)
    if getattr(args, "api_base", None):
        cfg.set("api_base", args.api_base)
    if getattr(args, "api_key", None):
        cfg.set("api_key", args.api_key)
    if getattr(args, "workspace", None):
        cfg.set("workspace", os.path.abspath(args.workspace))
    if getattr(args, "no_stream", False):
        cfg.set("stream", False)


def make_runtime(args: argparse.Namespace, llm_script=None) -> Runtime:
    setup_console()
    cfg = Config.load(getattr(args, "config", None))
    apply_cli_overrides(cfg, args)
    setup_logging(cfg.get("log_level", "INFO"), os.path.join(
        getattr(args, "home", None) or DEFAULT_HOME, "miniagent.log"))
    rt = Runtime(cfg, home=getattr(args, "home", None),
                 session=getattr(args, "session", None), llm_script=llm_script)
    rt.build()
    return rt


# ── 事件渲染 ────────────────────────────────────────────────
def render_event(kind: str, data: Any) -> None:
    if kind == "delta":
        sys.stdout.write(data)
        sys.stdout.flush()
    elif kind == "step":
        pass
    elif kind == "tool_call":
        name = data.get("name")
        args = data.get("arguments") or {}
        flag = " [需确认]" if data.get("risky") else ""
        sys.stdout.write("\n[调用] %s %s%s\n" % (name, short(args, 200), flag))
        sys.stdout.flush()
    elif kind == "tool_result":
        out = truncate(data.get("output", ""), 400)
        sys.stdout.write("[结果] %s\n" % out.replace("\n", "\n        "))
        sys.stdout.flush()
    elif kind == "error":
        sys.stdout.write("\n[错误] %s\n" % data)
    elif kind == "final":
        sys.stdout.write("\n")


def confirm_handler(tool: Tool, arguments: Dict[str, Any]) -> bool:
    print("\n[确认] 即将执行 %s(%s)" % (tool.name, short(arguments, 220)))
    try:
        ans = input("允许执行？[y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes", "是")


# ── 交互循环 ────────────────────────────────────────────────
def repl(rt: Runtime) -> int:
    agent = rt.agent
    assert agent is not None
    agent.on_event = render_event
    agent.confirm = confirm_handler
    print(BANNER % _version())
    print(rt.status())
    print("-" * 60)
    while True:
        try:
            line = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            return 0
        if not line:
            continue
        if line.lower() in EXIT_WORDS:
            print("再见。")
            return 0
        if line.startswith("/"):
            if handle_command(rt, line):
                return 0
            continue
        try:
            agent.chat(line, stream=bool(rt.cfg.get("stream", True)))
        except KeyboardInterrupt:
            print("\n（已中断）")
        except Exception as exc:
            LOG.exception("对话异常")
            print("[异常] %s: %s" % (type(exc).__name__, exc))


def handle_command(rt: Runtime, line: str) -> bool:
    """返回 True 表示退出。"""
    parts = line.split()
    cmd = parts[0].lower()
    arg = " ".join(parts[1:]).strip()
    cfg = rt.cfg
    if cmd in ("/help", "/?"):
        print(HELP)
    elif cmd == "/status":
        print(rt.status())
    elif cmd == "/tools":
        for t in rt.registry.all():
            if arg and arg.lower() not in (t.name + t.description).lower():
                continue
            req = ",".join(t.parameters.get("required", [])) or "-"
            print("- %s(%s) [%s] %s" % (t.name, req, t.source, t.description.split("\n")[0]))
    elif cmd == "/skills":
        print(rt.skills.catalog() or "（无技能）")
        print("技能目录: " + rt.skills.directory)
    elif cmd == "/plugins":
        print(rt.plugins.summary() if rt.plugins else "（无插件）")
    elif cmd == "/mcp":
        print(rt.mcp.summary())
    elif cmd == "/model":
        if not arg:
            print("当前模型: %s" % cfg.get("model"))
        else:
            cfg.set("model", arg)
            from .llm import create_llm
            rt.llm = create_llm(cfg)
            if rt.agent:
                rt.agent.llm = rt.llm
            print("已切换到 %s" % arg)
    elif cmd == "/config":
        _handle_config(rt, arg)
    elif cmd == "/new":
        rt.memory.clear()
        print("会话已清空")
    elif cmd == "/save":
        target = arg or os.path.join(rt.home, "export-%s.jsonl" % rt.memory.name)
        print("已导出: " + rt.memory.save_as(target))
    elif cmd == "/sessions":
        files = rt.memory.list_sessions(rt.home)
        print("\n".join(files) if files else "（暂无历史会话）")
    elif cmd == "/load":
        if not arg:
            print("用法: /load <会话文件名>")
        else:
            msgs = rt.memory.load(rt.home, arg)
            rt.memory.clear()
            for m in msgs:
                rt.memory.add(m.get("role", "user"), m.get("content", ""))
            print("已载入 %d 条消息" % len(msgs))
    elif cmd == "/reload":
        print(rt.reload_extensions())
    elif cmd == "/confirm":
        if arg == "on":
            cfg.set("auto_confirm", False)
            print("已开启确认")
        elif arg == "off":
            cfg.set("auto_confirm", True)
            print("已关闭确认（危险工具将直接执行）")
        else:
            print("用法: /confirm on|off")
    else:
        print("未知命令: %s（/help 查看帮助）" % cmd)
    return False


def _handle_config(rt: Runtime, arg: str) -> None:
    parts = arg.split()
    if not parts:
        print(json.dumps(rt.cfg.as_dict(), ensure_ascii=False, indent=2))
        return
    if len(parts) == 1:
        print("%s = %s" % (parts[0], json.dumps(rt.cfg.get(parts[0]), ensure_ascii=False)))
        return
    key, raw = parts[0], " ".join(parts[1:])
    value: Any = raw
    lowered = raw.lower()
    if lowered in ("true", "false"):
        value = (lowered == "true")
    else:
        try:
            value = json.loads(raw)
        except Exception:
            pass
    rt.cfg.set(key, value)
    rt.cfg.save()
    print("已设置 %s = %s（写入 %s）" % (key, json.dumps(value, ensure_ascii=False), rt.cfg.path))


def _version() -> str:
    from . import __version__
    return __version__


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print("MiniAgent %s" % _version())
        return 0
    if args.init:
        cfg = Config()
        path = cfg.save()
        print("已生成默认配置: %s" % path)
        return 0

    rt = make_runtime(args)
    agent = rt.agent
    assert agent is not None

    if args.list_tools:
        print(rt.registry.describe())
        return 0
    if args.web:
        from .webui import serve
        env_port = os.environ.get("PORT", "").strip()
        if env_port:
            # 云端/反向代理部署：监听注入的 PORT 并绑定 0.0.0.0
            return serve(rt, host="0.0.0.0", port=int(env_port), open_browser=False)
        return serve(rt, host=rt.cfg.get("webui.host", "127.0.0.1"),
                     port=args.port or int(rt.cfg.get("webui.port", 8787)))
    if args.prompt:
        agent.on_event = render_event
        agent.confirm = confirm_handler
        answer = agent.chat(args.prompt, stream=bool(rt.cfg.get("stream", True)))
        if not rt.cfg.get("stream", True):
            print(answer)
        return 0

    code = repl(rt)
    rt.shutdown()
    return code
