# -*- coding: utf-8 -*-
"""MiniAgent（灵枢）—— 可在 Windows 7 / 8.1 上运行的轻量级可扩展 AI Agent。

设计约束：
1. 只用 Python 标准库（requests 为可选加速依赖），Python 3.8+ 可跑；
2. 所有 I/O 显式声明 UTF-8，避免中文用户名 / GBK 控制台乱码；
3. 扩展点：工具（Tool）、插件（Plugin）、技能（Skill）、MCP 服务器（MCP）。
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
