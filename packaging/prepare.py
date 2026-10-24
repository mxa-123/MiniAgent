# -*- coding: utf-8 -*-
"""打包准备（仅标准库）。

职责：
  1. 暂存应用文件到 build/app
  2. 下载并解压嵌入式 Python 3.8 到 build/runtime（目标机零依赖）
  3. 可选：生成便携版 ZIP（dist/MiniAgent-portable.zip）

用法：
  python prepare.py                 # 暂存 app + runtime（安装包用）
  python prepare.py --portable     # 暂存并生成便携版 ZIP
  python prepare.py --runtime-only # 只下载运行时
"""
import argparse
import os
import shutil
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))   # packaging/
BUILD = os.path.join(ROOT, "build")
APP = os.path.join(BUILD, "app")
RUNTIME = os.path.join(BUILD, "runtime")            # 解压后 python.exe 在此
PROJ = os.path.dirname(ROOT)                         # 项目根（miniagent/）

PY_URLS = {
    "amd64": "https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip",
    "win32": "https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-win32.zip",
}

# 要打包的应用文件（相对项目根）
APP_ITEMS = ["run.py", "miniagent", "config", "plugins", "skills"]
SKIP_DIRS = {"__pycache__", ".git", "tests", "packaging", "build"}


def log(msg):
    print("[prepare] " + msg)


def stage_app():
    if os.path.isdir(APP):
        shutil.rmtree(APP)
    os.makedirs(APP)
    for item in APP_ITEMS:
        src = os.path.join(PROJ, item)
        if not os.path.exists(src):
            log("跳过（不存在）: %s" % item)
            continue
        dst = os.path.join(APP, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst)
    # 去掉可能误带入的 __pycache__
    for root, dirs, _ in os.walk(APP):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(root, "__pycache__"))
    log("应用文件已暂存: %s" % APP)


def _reporthook(block_num, block_size, total):
    if total <= 0:
        return
    done = block_num * block_size
    pct = min(100, done * 100 // total)
    sys.stdout.write("\r  下载进度: %d%%" % pct)
    sys.stdout.flush()


def stage_runtime(arch="amd64"):
    pyexe = os.path.join(RUNTIME, "python.exe")
    if os.path.isfile(pyexe):
        log("运行时已存在，跳过下载: %s" % pyexe)
        return
    url = PY_URLS[arch]
    os.makedirs(RUNTIME, exist_ok=True)
    tmp = os.path.join(BUILD, "python38.zip")
    log("下载嵌入式 Python 3.8 (%s)..." % arch)
    urllib.request.urlretrieve(url, tmp, _reporthook)
    print("")
    log("解压到 %s" % RUNTIME)
    with zipfile.ZipFile(tmp, "r") as z:
        z.extractall(RUNTIME)
    os.remove(tmp)
    if not os.path.isfile(pyexe):
        raise SystemExit("解压后未找到 python.exe，下载可能不完整")
    log("运行时就绪: %s" % pyexe)


def make_portable():
    import time
    stage_app()
    stage_runtime()
    portable = os.path.join(BUILD, "MiniAgent-portable")
    if os.path.isdir(portable):
        shutil.rmtree(portable)
    os.makedirs(portable)
    # app 文件 → 便携根
    for name in os.listdir(APP):
        s = os.path.join(APP, name)
        d = os.path.join(portable, name)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, d)
    # runtime → 便携根/python
    py_dir = os.path.join(portable, "python")
    os.makedirs(py_dir, exist_ok=True)
    for name in os.listdir(RUNTIME):
        s = os.path.join(RUNTIME, name)
        d = os.path.join(py_dir, name)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, d)
    # 启动脚本
    cli = os.path.join(portable, "MiniAgent-命令行.bat")
    web = os.path.join(portable, "MiniAgent-网页版.bat")
    with open(cli, "w", encoding="utf-8") as f:
        f.write("@echo off\r\ncd /d \"%~dp0\"\r\nstart \"\" python\\python.exe run.py %*\r\n")
    with open(web, "w", encoding="utf-8") as f:
        f.write("@echo off\r\ncd /d \"%~dp0\"\r\nstart \"\" python\\pythonw.exe run.py --web\r\n")
    # 打包成 zip
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    zip_path = os.path.join(dist, "MiniAgent-portable.zip")
    if os.path.isfile(zip_path):
        os.remove(zip_path)
    log("压缩便携版...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(portable):
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            for fn in files:
                fp = os.path.join(root, fn)
                z.write(fp, os.path.relpath(fp, portable))
    log("便携版已生成: %s (%d bytes)" % (zip_path, os.path.getsize(zip_path)))
    log("解压后双击 MiniAgent-网页版.bat 即可使用（无需安装 Python）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portable", action="store_true", help="生成便携版 ZIP")
    ap.add_argument("--runtime-only", action="store_true", help="只下载运行时")
    ap.add_argument("--arch", default="amd64", choices=["amd64", "win32"])
    args = ap.parse_args()

    if args.runtime_only:
        stage_runtime(args.arch)
        return
    stage_app()
    stage_runtime(args.arch)
    if args.portable:
        make_portable()


if __name__ == "__main__":
    main()
