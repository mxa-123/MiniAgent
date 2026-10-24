# -*- coding: utf-8 -*-
"""示例插件：展示两种扩展写法（@tool 自动收集 / setup(ctx) 手动注册）。

把这个文件放在 plugins/ 目录下即自动生效；改名、新增文件同理。
"""

from __future__ import annotations

import ast
import math
import os
import platform

from miniagent.tools import tool

# ── 写法一：@tool 装饰器，模块导入时自动被扫描 ──────────────


@tool(description="安全计算数学表达式，如 (12+8)*3.5 或 sqrt(16)")
def calc(expression: str) -> str:
    """计算数学表达式（只允许数字与常用数学函数，不执行任意代码）。
    :param expression: 表达式字符串
    """
    allowed = {k: getattr(math, k) for k in ("sqrt", "pow", "sin", "cos", "tan", "log", "log10",
                                             "pi", "e", "floor", "ceil", "radians", "degrees")}

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node):  # 只允许 math 里的具名函数
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed:
                raise ValueError("不允许调用函数: %s" % getattr(node.func, "id", "?"))
            self.generic_visit(node)

        def visit_Attribute(self, node):
            raise ValueError("不允许属性访问")

    tree = ast.parse(expression, mode="eval")
    _Visitor().visit(tree)
    result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, allowed)  # noqa: S307
    return "%s = %s" % (expression, result)


@tool(description="查看本机系统与资源概况（CPU / 内存 / 磁盘）")
def system_info() -> str:
    """返回操作系统、处理器、内存与磁盘剩余空间。"""
    lines = [
        "系统: %s %s (%s)" % (platform.system(), platform.release(), platform.machine()),
        "处理器: %s" % (platform.processor() or "未知"),
        "Python: %s" % platform.python_version(),
        "工作目录: %s" % os.getcwd(),
    ]
    mem = _memory()
    if mem:
        lines.append("内存: 已用 %.1f GB / 共 %.1f GB (%.0f%%)" % mem)
    disk = _disk()
    if disk:
        lines.append("磁盘: 剩余 %.1f GB" % disk)
    return "\n".join(lines)


def _memory():
    try:
        if os.name == "nt":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total = stat.ullTotalPhys / 1024.0 ** 3
            avail = stat.ullAvailPhys / 1024.0 ** 3
            return (total - avail, total, stat.dwMemoryLoad)
        with open("/proc/meminfo") as fh:
            info = dict(line.split(":", 1) for line in fh.read().splitlines() if ":" in line)
        total = int(info["MemTotal"].split()[0]) / 1024.0 ** 2
        avail = int(info.get("MemAvailable", info["MemTotal"]).split()[0]) / 1024.0 ** 2
        return (total - avail, total, (total - avail) / total * 100)
    except Exception:
        return None


def _disk():
    try:
        if hasattr(os, "statvfs"):
            st = os.statvfs(os.getcwd())
            return st.f_bavail * st.f_frsize / 1024.0 ** 3
        import ctypes
        free = ctypes.c_ulonglong()
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar(os.getcwd()[:2] + "\\"),
                                                   None, None, ctypes.byref(free))
        return free.value / 1024.0 ** 3
    except Exception:
        return None


# ── 写法二：setup(ctx) —— 需要读配置、用记忆、发事件时用这种 ──


def setup(ctx):
    """ctx 提供：cfg（配置）/ registry（工具表）/ memory（记忆）/ emit（事件）/ agent。"""
    workspace = os.path.abspath(ctx.cfg.get("workspace", "."))

    @tool(description="统计指定目录里各文件类型的数量与总大小")
    def dir_stats(path: str = ".", top: int = 8) -> str:
        """按扩展名统计目录下文件数量与体积。
        :param path: 目录路径
        :param top: 显示前几名
        """
        base = path if os.path.isabs(path) else os.path.join(workspace, path)
        agg = {}
        for root, _dirs, files in os.walk(base):
            for f in files:
                ext = os.path.splitext(f)[1].lower() or "(无扩展名)"
                try:
                    size = os.path.getsize(os.path.join(root, f))
                except Exception:
                    size = 0
                c, s = agg.get(ext, (0, 0))
                agg[ext] = (c + 1, s + size)
        rows = sorted(agg.items(), key=lambda kv: kv[1][1], reverse=True)[:top]
        return "\n".join("%-14s %5d 个  %8.2f MB" % (k, c, s / 1024.0 ** 2) for k, (c, s) in rows) or "（空目录）"

    ctx.registry.register_func(dir_stats, source="plugin:example")
