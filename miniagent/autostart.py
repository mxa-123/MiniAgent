# -*- coding: utf-8 -*-
"""开机自启（Win7 / Win8.1 通用）。

只用 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 写字符串值：
Win7 上写 .vbs/.bat 到启动文件夹会被安全策略拦，COM 建快捷方式同样被拦，
注册表 Run 键是这台机器上唯一可靠的路径（见用户级记忆「主机环境约束」）。

不申请管理员权限，装到 %LOCALAPPDATA% 的版本照样能自启。
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

RUN_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"
VALUE_NAME = "MiniAgent"


def _launcher() -> Tuple[str, str]:
    """返回 (可执行文件, 脚本路径)。脚本为空表示直接跑 exe。"""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    pyw = os.path.join(exe_dir, "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    here = os.path.dirname(os.path.abspath(__file__))
    # <安装目录>/miniagent/autostart.py -> <安装目录>/desktop.py
    script = os.path.join(os.path.dirname(here), "desktop.py")
    if not os.path.exists(script):
        script = ""
    return pyw, script


def command_line() -> str:
    """拼出注册表里要写的那条命令。"""
    exe, script = _launcher()
    if script:
        return '"%s" "%s"' % (exe, script)
    return '"%s"' % exe


def is_enabled() -> bool:
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        return bool(value)
    except OSError:
        return False


def enable() -> str:
    """打开自启，返回写入的命令。"""
    import winreg
    cmd = command_line()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    return cmd


def disable() -> None:
    """关闭自启（键不存在时静默成功）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass


def toggle() -> bool:
    """开关自启，返回切换后的状态。"""
    if is_enabled():
        disable()
        return False
    enable()
    return True


def describe() -> str:
    """给界面显示的一行说明。"""
    if is_enabled():
        return "开机自启：已开启"
    return "开机自启：已关闭"


if __name__ == "__main__":
    state = toggle()
    print(describe())
    print(command_line())
    sys.exit(0 if state else 1)
