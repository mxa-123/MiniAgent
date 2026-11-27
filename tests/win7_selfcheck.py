# -*- coding: utf-8 -*-
"""MiniAgent 一键自检（Win7 / Win8.1 / 32 位）。

在目标机上双击 `MiniAgent-SelfCheck.bat` 或运行本脚本即可，
逐项打印 PASS / FAIL，把结论写到 `~/.miniagent/selfcheck.txt`。

不联网、不改用户数据（自启开关会被还原）。
"""

from __future__ import print_function

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT_DIR = os.path.join(os.path.expanduser("~"), ".miniagent")
OUT_FILE = os.path.join(OUT_DIR, "selfcheck.txt")
_lines = []


def record(ok, name, detail=""):
    tag = "PASS" if ok else "FAIL"
    line = "[%s] %s%s" % (tag, name, ("  -> " + detail) if detail else "")
    _lines.append(line)
    print(line)
    return ok


def main():
    print("MiniAgent 自检 — Python %s" % sys.version.split()[0])
    try:
        os.chdir(ROOT)
    except Exception:
        pass
    bits = 32 if sys.maxsize < 2 ** 32 else 64
    record(True, "Python 版本", "%s (%d 位)" % (sys.version.split()[0], bits))

    # 1. tkinter
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.update()
        tv = tk.TkVersion
        root.destroy()
        record(True, "tkinter 图形界面", "Tk %s" % tv)
    except Exception as exc:
        record(False, "tkinter 图形界面", "%s: %s" % (type(exc).__name__, exc))

    # 2. SQLite 持久化
    try:
        from miniagent import db
        db.init_db()
        sid = db.create_session("__自检临时会话__")
        db.add_message(sid, "user", "ping")
        db.add_trace(sid, "plan", "自检")
        msgs = db.list_messages(sid)
        tr = db.list_trace(sid)
        db.delete_session(sid)
        record(len(msgs) == 1 and len(tr) == 1, "SQLite 会话 / 消息 / 轨迹",
               "库: %s" % db.db_path())
    except Exception as exc:
        record(False, "SQLite 会话 / 消息 / 轨迹",
               "%s: %s" % (type(exc).__name__, exc))

    # 3. 插件系统
    try:
        from miniagent.plugins import PluginManager
        record(True, "插件系统可加载")
    except Exception as exc:
        record(False, "插件系统可加载", "%s: %s" % (type(exc).__name__, exc))

    # 4. 开机自启（写完立刻还原）
    try:
        from miniagent import autostart
        before = autostart.is_enabled()
        autostart.enable()
        on = autostart.is_enabled()
        autostart.disable()
        record(on and not autostart.is_enabled(), "开机自启（注册表 Run 键）",
               "命令: %s" % autostart.command_line())
        if before:
            autostart.enable()
    except Exception as exc:
        record(False, "开机自启（注册表 Run 键）",
               "%s: %s" % (type(exc).__name__, exc))

    # 5. 内核与工具
    try:
        from miniagent.runtime import Runtime
        from miniagent.config import Config
        rt = Runtime(Config({"provider": "mock", "model": "演示模式"}), home=OUT_DIR)
        rt.build()
        n = len(rt.registry.names())
        rt.shutdown()
        record(n > 0, "运行时与工具注册", "%d 个工具" % n)
    except Exception as exc:
        record(False, "运行时与工具注册",
               "%s: %s" % (type(exc).__name__, exc))

    # 6. CLI 无人值守
    try:
        import subprocess
        exe = os.path.join(ROOT, "python", "python.exe")
        if not os.path.exists(exe):
            exe = sys.executable
        proc = subprocess.run(
            [exe, os.path.join(ROOT, "run.py"), "-p", "自检", "-y",
             "--provider", "mock", "--model", "演示模式", "--no-stream"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        text = (proc.stdout or b"").decode("utf-8", "replace")
        record(proc.returncode == 0 and "完成" in text, "CLI 无人值守（-y）",
               "退出码 %d" % proc.returncode)
    except Exception as exc:
        record(False, "CLI 无人值守（-y）", "%s: %s" % (type(exc).__name__, exc))

    passed = sum(1 for x in _lines if x.startswith("[PASS]"))
    failed = len(_lines) - passed
    summary = "=== 汇总: %d/%d 通过 ===" % (passed, len(_lines))
    print(summary)
    _lines.append(summary)
    try:
        if not os.path.isdir(OUT_DIR):
            os.makedirs(OUT_DIR)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines) + "\n")
        print("结果已写入: %s" % OUT_FILE)
    except Exception:
        traceback.print_exc()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
