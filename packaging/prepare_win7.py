# -*- coding: utf-8 -*-
"""Win7 兼容版便携包生成（仅标准库）。

和 prepare.py 的区别只有一处：内置运行时用 Python 3.7.9 而不是 3.8.10。

原因（2026-11 实测确认）：
  Python 3.8 引入了 SetDefaultDllDirectories / LOAD_LIBRARY_SEARCH_* 安全加载，
  该 API 在 Windows 7 上依赖补丁 KB2533623。裸 Win7 SP1 没这个补丁时，
  import _ssl 会报 "DLL load failed ... 参数错误"，导致 MiniAgent 直接退出。
  Python 3.7 用老式 LoadLibrary，不需要 KB2533623，所以换 3.7 就绕开了。

用法：
  python prepare_win7.py                  # 生成便携包（文件夹 + zip）
  python prepare_win7.py --no-zip         # 只生成文件夹，不压 zip
  python prepare_win7.py --arch win32     # 32 位 Win7
  python prepare_win7.py --clean          # 删掉缓存的运行时重新下载

输出：
  build/MiniAgent-portable-win7/          便携文件夹（拷走即用）
  dist/MiniAgent-portable-win7.zip        压缩包
"""
import argparse
import os
import shutil
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))       # packaging/
BUILD = os.path.join(ROOT, "build")
APP = os.path.join(BUILD, "app_win7")
RUNTIME = os.path.join(BUILD, "runtime37")              # 解压后 python.exe 在此
PROJ = os.path.dirname(ROOT)                            # 项目根

PY_VER = "3.7.9"
# 主站优先，失败自动退到华为镜像（国内更快）
PY_URLS = {
    "amd64": [
        "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (PY_VER, PY_VER),
        "https://mirrors.huaweicloud.com/python/%s/python-%s-embed-amd64.zip" % (PY_VER, PY_VER),
    ],
    "win32": [
        "https://www.python.org/ftp/python/%s/python-%s-embed-win32.zip" % (PY_VER, PY_VER),
        "https://mirrors.huaweicloud.com/python/%s/python-%s-embed-win32.zip" % (PY_VER, PY_VER),
    ],
}

APP_ITEMS = ["run.py", "miniagent", "config", "plugins", "skills"]
SKIP_DIRS = {"__pycache__", ".git", "tests", "packaging", "build"}

README_NAME = "Win7兼容说明.txt"
README_TEXT = """MiniAgent Win7 兼容版
========================================

本包内置 Python {ver}，用于 Windows 7 SP1 系统。
MiniAgent 源码未做任何修改。

为什么不用原来的 Python 3.8
----------------------------------------
Python 3.8 改了 DLL 安全加载方式（SetDefaultDllDirectories /
LOAD_LIBRARY_SEARCH_*），这套 API 在 Win7 上要靠补丁 KB2533623 才有。
裸 Win7 没这个补丁时，import _ssl 会报：
    ImportError: DLL load failed while importing _ssl: 参数错误
于是 MiniAgent 一启动就退出。Python 3.7 不需要该补丁。

用法
----------------------------------------
1. 整个文件夹拷到旧电脑（U 盘即可，无需安装）
2. MiniAgent-CLI.bat   命令行版
   MiniAgent-Web.bat   网页版（浏览器打开 http://127.0.0.1:8787）
3. 配置在 config 目录

如果提示缺少 api-ms-win-crt-*.dll / ucrtbase.dll
----------------------------------------
说明这台 Win7 从没更新过，双击本目录的 vc_redist.x64.exe 装一次即可
（32 位系统请用 vc_redist.x86.exe），装完重启。

已知限制
----------------------------------------
- 本包为 {arch} 架构，请在对应位数的 Win7 上使用
- 若源码引入了 3.8+ 语法或新版第三方库，需重新打包并检查兼容性
  检查命令: python packaging/check_win7_compat.py
"""

LAUNCHER_CLI = (
    "@echo off\r\n"
    "chcp 65001 >nul\r\n"
    "cd /d \"%~dp0\"\r\n"
    "REM 不加 start，崩溃时窗口会留住并显示报错，方便排查\r\n"
    "python\\python.exe run.py %*\r\n"
    "echo.\r\n"
    "echo [exit code: %errorlevel%]\r\n"
    "pause\r\n"
)

LAUNCHER_WEB = (
    "@echo off\r\n"
    "chcp 65001 >nul\r\n"
    "cd /d \"%~dp0\"\r\n"
    "start \"\" python\\pythonw.exe run.py --web\r\n"
    "echo Web UI: http://127.0.0.1:8787\r\n"
    "timeout /t 3 >nul\r\n"
)


def log(msg):
    print("[win7] " + msg)


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
    for root, dirs, _ in os.walk(APP):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(root, "__pycache__"))
            dirs.remove("__pycache__")
    log("应用文件已暂存: %s" % APP)


def _reporthook(block_num, block_size, total):
    if total <= 0:
        return
    pct = min(100, block_num * block_size * 100 // total)
    sys.stdout.write("\r  下载进度: %d%%" % pct)
    sys.stdout.flush()


def stage_runtime(arch="amd64", clean=False):
    pyexe = os.path.join(RUNTIME, "python.exe")
    if clean and os.path.isdir(RUNTIME):
        log("清除旧运行时缓存")
        shutil.rmtree(RUNTIME)
    if os.path.isfile(pyexe):
        log("运行时已存在，跳过下载: %s" % pyexe)
        return
    os.makedirs(RUNTIME, exist_ok=True)
    tmp = os.path.join(BUILD, "python37-%s.zip" % arch)
    last_err = None
    for url in PY_URLS[arch]:
        try:
            log("下载嵌入式 Python %s (%s): %s" % (PY_VER, arch, url))
            urllib.request.urlretrieve(url, tmp, _reporthook)
            print("")
            if os.path.getsize(tmp) > 3 * 1024 * 1024:
                break
            last_err = "文件过小，可能下载失败"
        except Exception as e:      # noqa: BLE001
            last_err = str(e)
            log("该源失败: %s" % e)
            continue
    else:
        raise SystemExit("所有下载源都失败: %s" % last_err)

    log("解压到 %s" % RUNTIME)
    with zipfile.ZipFile(tmp, "r") as z:
        z.extractall(RUNTIME)
    os.remove(tmp)
    if not os.path.isfile(pyexe):
        raise SystemExit("解压后未找到 python.exe，下载可能不完整")
    log("运行时就绪: %s" % pyexe)


def write_vc_redist_target(portable, arch):
    """把 vc_redist 的下载提示写进说明；若本地有安装包就一起拷进去。"""
    names = ["vc_redist.x64.exe"] if arch == "amd64" else ["vc_redist.x86.exe"]
    found = False
    for base in (os.path.join(ROOT, "assets"), os.path.join(BUILD, "runtime37")):
        for nm in names:
            src = os.path.join(base, nm)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(portable, nm))
                log("已附带 %s" % nm)
                found = True
    if not found:
        log("未找到 %s（可选）。需要时从 https://aka.ms/vs/17/release/ 下载"
            % "/".join(names))


def make_portable(arch="amd64", want_zip=True):
    stage_app()
    stage_runtime(arch)
    portable = os.path.join(BUILD, "MiniAgent-portable-win7")
    if os.path.isdir(portable):
        shutil.rmtree(portable)
    os.makedirs(portable)
    for name in os.listdir(APP):
        s = os.path.join(APP, name)
        d = os.path.join(portable, name)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, d)

    py_dir = os.path.join(portable, "python")
    os.makedirs(py_dir, exist_ok=True)
    for name in os.listdir(RUNTIME):
        s = os.path.join(RUNTIME, name)
        d = os.path.join(py_dir, name)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, d)

    # 启动脚本：英文名 + 避免 Win7 的 GBK 乱码
    with open(os.path.join(portable, "MiniAgent-CLI.bat"), "w", encoding="utf-8", newline="") as f:
        f.write(LAUNCHER_CLI)
    with open(os.path.join(portable, "MiniAgent-Web.bat"), "w", encoding="utf-8", newline="") as f:
        f.write(LAUNCHER_WEB)

    with open(os.path.join(portable, README_NAME), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(README_TEXT.format(ver=PY_VER, arch=arch))

    write_vc_redist_target(portable, arch)

    log("便携目录: %s" % portable)
    if not want_zip:
        return portable

    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    zip_path = os.path.join(dist, "MiniAgent-portable-win7.zip")
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
    log("已生成: %s (%d bytes)" % (zip_path, os.path.getsize(zip_path)))
    return portable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arch", default="amd64", choices=["amd64", "win32"])
    ap.add_argument("--no-zip", action="store_true", help="只生成文件夹")
    ap.add_argument("--clean", action="store_true", help="清掉运行时缓存重新下载")
    args = ap.parse_args()

    if args.clean:
        stage_runtime(args.arch, clean=True)
    make_portable(args.arch, want_zip=not args.no_zip)
    log("完成。建议接着跑: python packaging/check_win7_compat.py")


if __name__ == "__main__":
    main()
