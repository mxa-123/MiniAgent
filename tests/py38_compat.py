# -*- coding: utf-8 -*-
"""Python 3.8 兼容性静态检查（Win7 能用的最后一版 Python）。

做法：
1. 用 ast.parse(feature_version=(3,8)) 校验语法（能挡住 match / PEP584 等新语法）；
2. 正则扫描 3.9+ 才有的标准库 API 与写法。

运行： python tests/py38_compat.py
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANNED = [
    (r"removeprefix\s*\(", "str.removeprefix (3.9+)"),
    (r"removesuffix\s*\(", "str.removesuffix (3.9+)"),
    (r"\bimport\s+zoneinfo\b", "zoneinfo (3.9+)"),
    (r"\bimport\s+graphlib\b", "graphlib (3.9+)"),
    (r"functools\.cache\b", "functools.cache (3.9+)"),
    (r"math\.lcm\b", "math.lcm (3.9+)"),
    (r"\bmatch\s+.*:\s*$", "match 语句 (3.10+)"),
    (r":\s*(list|dict|tuple|set)\[", "PEP585 内置泛型下标 (3.9+，注解里请用 typing)"),
]


def main():
    problems = []
    files = []
    for base, dirs, names in os.walk(os.path.join(ROOT, "miniagent")):
        dirs[:] = [d for d in dirs if not d.startswith("__")]
        for n in names:
            if n.endswith(".py"):
                files.append(os.path.join(base, n))
    for f in [os.path.join(ROOT, "run.py"),
              os.path.join(ROOT, "tests", "smoke_test.py"),
              os.path.join(ROOT, "tests", "mock_mcp_server.py"),
              os.path.join(ROOT, "plugins", "example_tools.py")]:
        if os.path.isfile(f):
            files.append(f)

    for path in files:
        src = open(path, "rb").read().decode("utf-8")
        try:
            ast.parse(src, filename=path, feature_version=(3, 8))
        except SyntaxError as exc:
            problems.append("%s: 语法不兼容 3.8 -> %s (行 %s)" % (path, exc.msg, exc.lineno))
        for pattern, why in BANNED:
            for m in re.finditer(pattern, src, re.M):
                line = src[:m.start()].count("\n") + 1
                # 允许出现在注释/文档字符串里的说明文字
                seg = src.splitlines()[line - 1].strip()
                if seg.startswith("#") or seg.startswith(("\"", "'", "u\"", "r\"")):
                    continue
                problems.append("%s:%d: 使用了 %s" % (path, line, why))

    print("检查 %d 个文件" % len(files))
    if problems:
        for p in problems:
            print("FAIL " + p)
        print("\n%d 处不兼容" % len(problems))
        return 1
    print("全部通过：语法与 API 均兼容 Python 3.8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
