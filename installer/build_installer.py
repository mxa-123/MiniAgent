# -*- coding: utf-8 -*-
"""一键构建 MiniAgent 安装包。

流程：PyInstaller 打 desktop.py -> NSIS 打包 -> dist/MiniAgent-安装包.exe
降级：PyInstaller 不可用或失败时，NSIS 改安装源码 + pythonw 启动器。
约束：纯标准库；语法兼容 Python 3.7 / 3.8；不执行生成的安装程序。

兼容事实（务必如实告知用户）：
  本机 Python 3.14 是 64 位，PyInstaller 6.x 产物只支持 64 位 Win8+/Win10/Win11，
  不支持 Win7、也不支持 32 位。
  Win7 / 32 位构建路径（本脚本不使用，仅预留）：
    Python 3.8.10 (32 位) + PyInstaller 4.10，再编译同一个 installer/MiniAgent.nsi。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
SPEC = os.path.join(ROOT, "MiniAgent.spec")
APP_NAME = "MiniAgent"
FROZEN_EXE = APP_NAME + ".exe"
SETUP_ASCII = "MiniAgent-Setup.exe"
SETUP_FINAL = "MiniAgent-\u5b89\u88c5\u5305.exe"

# 唯一允许出现的绝对路径：本机已装好的 NSIS 编译器。
NSIS_CANDIDATES = [
    os.environ.get("MINIAGENT_MAKENSIS", ""),
    "C:\\Program Files (x86)\\NSIS\\makensis.exe",
    "C:\\Program Files\\NSIS\\makensis.exe",
]


def _run(cmd: List[str], label: str) -> Tuple[int, str]:
    """执行外部命令并回显输出，供构建日志与排错使用。"""
    print("[%s] %s" % (label, " ".join(cmd)))
    sys.stdout.flush()
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        raw, _ = proc.communicate()
        text = raw.decode("utf-8", "replace") if raw else ""
    except Exception as exc:
        return 1, "无法启动命令：%s" % exc
    if text:
        print(text[-6000:])
    return int(proc.returncode), text


def _pyinstaller_ok(python_exe: str) -> bool:
    try:
        proc = subprocess.Popen([python_exe, "-m", "PyInstaller", "--version"],
                                cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        raw, _ = proc.communicate()
        return int(proc.returncode) == 0 and bool(raw)
    except Exception:
        return False


def _find_python() -> Optional[str]:
    candidates: List[str] = []
    env_py = os.environ.get("MINIAGENT_BUILD_PYTHON", "")
    if env_py:
        candidates.append(env_py)
    candidates.append(sys.executable)
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    seen: List[str] = []
    for item in candidates:
        if item and os.path.isfile(item) and item not in seen:
            seen.append(item)
    for item in seen:
        if _pyinstaller_ok(item):
            return item
    return None


def _find_makensis() -> Optional[str]:
    candidates: List[str] = list(NSIS_CANDIDATES)
    found = shutil.which("makensis")
    if found:
        candidates.append(found)
    for item in candidates:
        if item and os.path.isfile(item):
            return item
    return None


def _clean_temp() -> None:
    """只清理本次构建产生的中间物，不动 dist 里的其它文件。"""
    frozen = os.path.join(DIST, FROZEN_EXE)
    if os.path.isfile(frozen):
        try:
            os.remove(frozen)
        except OSError:
            pass
    shutil.rmtree(os.path.join(BUILD, APP_NAME), ignore_errors=True)
    try:
        os.rmdir(BUILD)  # 仅当已空
    except OSError:
        pass
    for path in (SPEC,):
        try:
            os.remove(path)
        except OSError:
            pass
    for path in (os.path.join(ROOT, "__pycache__"),
                 os.path.join(ROOT, "installer", "__pycache__")):
        shutil.rmtree(path, ignore_errors=True)


def _build_frozen(python_exe: str) -> bool:
    # Windows 上 PyInstaller 的 --add-data 分隔符是分号；os.pathsep 在 Windows 正好是 ";"
    sep = os.pathsep
    cmd = [
        python_exe, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", APP_NAME,
        "--distpath", "dist",
        "--workpath", os.path.join("build", APP_NAME),
        "--specpath", ".",
        "--add-data", "config" + sep + "config",
        "--add-data", "skills" + sep + "skills",
        "--add-data", "plugins" + sep + "plugins",
        "--paths", ".",
        "desktop.py",
    ]
    code, _ = _run(cmd, "PyInstaller")
    exe = os.path.join(DIST, FROZEN_EXE)
    if code != 0 or not os.path.isfile(exe):
        return False
    print("[*] 冻结程序：%s（%.2f MB）"
          % (exe, os.path.getsize(exe) / 1024.0 / 1024.0))
    return True


def _selftest_frozen(exe: str) -> str:
    """可选：让冻结 exe 跑一次无窗口自检，确认 Tcl/Tk 与扩展目录都找得到。

    不弹窗口、不写用户配置、不执行安装程序。默认关闭，用
    MINIAGENT_RUN_SELFTEST=1 开启。
    """
    tmp = tempfile.mkdtemp(prefix="miniagent_frozen_")
    report = os.path.join(tmp, "selftest.txt")
    env = dict(os.environ)
    env["MINIAGENT_SELFTEST"] = report
    try:
        proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), env=env,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return "[!] frozen exe self-test timed out"
        if os.path.isfile(report):
            with open(report, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read().strip()
        return "[!] frozen exe self-test produced no report (exit=%s)" % proc.returncode
    except Exception as exc:
        return "[!] frozen exe self-test could not run: %s" % exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _compile_nsis(makensis: str, source_mode: bool) -> bool:
    cmd = [makensis, "/V2"]
    if source_mode:
        cmd.append("/DMINIAGENT_SOURCE_MODE")
    cmd.append(os.path.join("installer", "MiniAgent.nsi"))
    code, _ = _run(cmd, "NSIS")
    return code == 0 and os.path.isfile(os.path.join(DIST, SETUP_ASCII))


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if not os.path.isdir(DIST):
        os.makedirs(DIST)
    os.chdir(ROOT)
    _clean_temp()

    python_exe = _find_python()
    mode = "exe"
    if python_exe is None:
        print("[!] 没找到可用的 PyInstaller，改用源码安装模式。")
        mode = "source"
    elif not _build_frozen(python_exe):
        print("[!] PyInstaller 打包失败（常见于 PyInstaller 6.x 与 Python 3.14 不兼容），改用源码安装模式。")
        mode = "source"

    if mode == "exe" and os.environ.get("MINIAGENT_RUN_SELFTEST", "").strip():
        print("")
        print("=== 冻结 exe 无窗口自检 ===")
        print(_selftest_frozen(os.path.join(DIST, FROZEN_EXE)))
        print("")

    makensis = _find_makensis()
    if makensis is None:
        print("[X] 没找到 makensis.exe（NSIS 编译器），无法生成安装包。")
        return 1

    if not _compile_nsis(makensis, mode == "source"):
        print("[X] NSIS 编译失败，请看上方输出。")
        return 1

    src = os.path.join(DIST, SETUP_ASCII)
    final = os.path.join(DIST, SETUP_FINAL)
    try:
        if os.path.isfile(final):
            os.remove(final)
        os.replace(src, final)
    except (OSError, UnicodeError) as exc:
        print("[!] 中文名重命名失败（%s），保留英文名：%s" % (exc, src))
        final = src

    # NSIS 已经把 MiniAgent.exe 打进安装包，中间物用完即清，dist 只留成品
    _clean_temp()

    size = os.path.getsize(final)
    if size < 100 * 1024:
        print("[X] 安装包体积异常（%d 字节），构建可能不完整。" % size)
        return 1

    print("")
    print("=== 构建完成 ===")
    print("安装包：%s" % final)
    print("大小：%.2f MB" % (size / 1024.0 / 1024.0))
    print("SHA256：%s" % _sha256(final))
    print("模式：%s" % ("自带 Python 的独立 exe" if mode == "exe" else "源码 + 系统 Python（需已安装 Python 3.8+）"))
    print("")
    print("[i] 兼容性提醒：本安装包是 64 位，仅支持 Windows 8 / 10 / 11。")
    print("[i] 它不支持 Windows 7，也不支持 32 位系统。")
    print("[i] Win7 / 32 位构建路径（本脚本未使用）：Python 3.8.10 32 位 + PyInstaller 4.10，")
    print("    再用同一个 installer/MiniAgent.nsi 编译即可。")
    print("[i] 安装包只做了编译与完整性检查，没有执行，也不会装到这台电脑上。")
    print("")
    print("dist/ 目录内容：")
    for name in sorted(os.listdir(DIST)):
        path = os.path.join(DIST, name)
        if os.path.isfile(path):
            print("  %-40s %10d bytes" % (name, os.path.getsize(path)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
