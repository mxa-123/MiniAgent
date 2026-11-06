# -*- coding: utf-8 -*-
"""检查源码是否仍然能在 Python 3.7（Win7 兼容运行时）上跑。

以后每次改完 MiniAgent 源码，打包 Win7 版之前跑一下这个。

四道检查：
  1. 语法层：ast.parse(feature_version=(3,7)) —— 命中 3.8+ 语法会直接报
  2. 真编译：用内置 3.7 运行时 python -m compileall 编译所有 .py
  3. API 层：扫描 3.8 / 3.9 才有的运行时 API（ast 查不出来的）
  4. 冒烟：用 3.7 运行 packaed 包跑 run.py --list-tools

用法：
  python packaging/check_win7_compat.py
  python packaging/check_win7_compat.py --src-only     # 跳过冒烟（还没打包时）
"""
import argparse
import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(ROOT)
PORTABLE = os.path.join(ROOT, "build", "MiniAgent-portable-win7")
SCAN_DIRS = ["miniagent", "plugins", "skills"]

# 3.8+ 才有的运行时 API，ast 语法检查抓不到，只能靠文本扫描
API_RULES = [
    (r"\bmath\.prod\s*\(", "math.prod（3.8+）"),
    (r"\bfunctools\.cached_property\b", "functools.cached_property（3.8+）"),
    (r"\.removeprefix\s*\(", "str.removeprefix（3.9+）"),
    (r"\.removesuffix\s*\(", "str.removesuffix（3.9+）"),
    (r"\b(?:dict|list|set)\s*\[\s*str\s*,", "内置泛型下标 dict[str, ...]（3.9+ 运行时才支持）"),
    (r"\bfrom typing import .*\b(Literal|TypedDict|Protocol|Final)\b",
     "typing.Literal/TypedDict/Protocol/Final（3.8+）"),
    (r"\bzoneinfo\b", "zoneinfo（3.9+）"),
    (r"\basyncio\.to_thread\b", "asyncio.to_thread（3.9+）"),
    (r"\bgraphlib\b", "graphlib（3.9+）"),
]

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"


def ok(m):
    print(GREEN + "  [OK] " + RESET + m)


def bad(m):
    print(RED + "  [!!] " + RESET + m)


def warn(m):
    print(YELLOW + "  [??] " + RESET + m)


def iter_py_files():
    for d in SCAN_DIRS:
        base = os.path.join(PROJ, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            for fn in files:
                if fn.endswith(".py"):
                    yield os.path.join(root, fn)
    rp = os.path.join(PROJ, "run.py")
    if os.path.isfile(rp):
        yield rp


def check_syntax(files):
    print("\n[1/4] 语法层（Python 3.7 语法）")
    fails = 0
    for f in files:
        try:
            src = open(f, encoding="utf-8", errors="replace").read()
        except OSError as e:
            bad("%s 读取失败: %s" % (f, e))
            fails += 1
            continue
        try:
            ast.parse(src, filename=f, feature_version=(3, 7))
        except SyntaxError as e:
            bad("%s:%s  %s" % (os.path.relpath(f, PROJ), e.lineno, e.msg))
            fails += 1
    if fails == 0:
        ok("全部 %d 个文件通过 3.7 语法检查" % len(list(files)))
    return fails


def check_api(files):
    print("\n[2/4] API 层（3.8+ 运行时 API 扫描）")
    hits = 0
    for f in files:
        try:
            lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat, desc in API_RULES:
                if re.search(pat, line):
                    warn("%s:%d  用了 %s" % (os.path.relpath(f, PROJ), i, desc))
                    print(DIM + "        " + stripped[:110] + RESET)
                    hits += 1
    if hits == 0:
        ok("没有发现 3.8+ 专属运行时 API")
    else:
        print(DIM + "  以上若确实用到，Win7(3.7) 上会抛 AttributeError/ImportError" + RESET)
    return hits


def check_compile():
    print("\n[3/4] 真编译（用内置 3.7 运行时 compileall）")
    pyexe = os.path.join(PORTABLE, "python", "python.exe")
    if not os.path.isfile(pyexe):
        warn("未找到打包后的运行时，跳过。先跑: python packaging/prepare_win7.py")
        return None
    code = (
        "import compileall,sys;"
        "ok=compileall.compile_dir(sys.argv[1],quiet=1,force=True);"
        "sys.exit(0 if ok else 1)"
    )
    rc = 0
    for d in SCAN_DIRS:
        base = os.path.join(PORTABLE, d)
        if not os.path.isdir(base):
            continue
        r = subprocess.run([pyexe, "-c", code, base],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            bad("%s 编译失败" % d)
            print(r.stdout.decode("utf-8", "replace")[:800])
            rc = 1
    if rc == 0:
        ok("3.7 运行时编译通过")
    return rc


def check_smoke():
    print("\n[4/4] 冒烟（3.7 运行 run.py --list-tools）")
    pyexe = os.path.join(PORTABLE, "python", "python.exe")
    if not os.path.isfile(pyexe):
        warn("未找到打包后的运行时，跳过")
        return None
    r = subprocess.run([pyexe, "run.py", "--list-tools"], cwd=PORTABLE,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace")
    if r.returncode == 0:
        n = len([ln for ln in out.splitlines() if ln.startswith("- ")])
        ok("启动成功，列出 %d 个工具" % n)
        return 0
    bad("启动失败，退出码 %d" % r.returncode)
    print(DIM + out[-1500:] + RESET)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-only", action="store_true", help="只做源码检查，不跑打包产物")
    args = ap.parse_args()

    files = list(iter_py_files())
    if not files:
        bad("没有找到任何 .py 文件，检查 PROJ 路径: %s" % PROJ)
        return 2

    print("检查 %d 个源文件，目标运行时 Python 3.7.9 (Win7)" % len(files))
    f1 = check_syntax(files)
    f2 = check_api(files)

    f3 = f4 = None
    if not args.src_only:
        f3 = check_compile()
        f4 = check_smoke()

    print("\n" + "=" * 52)
    problems = [x for x in (f1, f2, f3, f4) if x]
    if problems:
        print(RED + "结论：有 %d 项需要处理，Win7 上可能跑不起来" % len(problems) + RESET)
        return 1
    print(GREEN + "结论：全部通过，可以打包给 Win7 用" + RESET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
