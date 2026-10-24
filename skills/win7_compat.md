---
name: Win7 兼容性检查
description: 检查 Python 代码/脚本在 Windows 7 + Python 3.8 上能否运行，给出替换方案
---

# Windows 7 / 8.1 兼容性检查清单

目标环境：**Windows 7 SP1 / 8.1 + Python 3.8.10（Win7 能用的最后一版 Python）**。

逐项检查并输出结论：

1. **语法**：禁止 `match` 语句、`dict | dict`、`list[str]` 运行时下标、`str.removeprefix`、海象运算符以外的 3.8+ 新语法。
   - 替代：类型注解用 `typing.List/Dict/Optional`。
2. **标准库**：`zoneinfo`（3.9+）、`graphlib`（3.9+）不可用 → 用 `pytz` 或自己实现。
3. **子进程**：`subprocess` 不用 `capture_output` 以外的 3.7+ 新参数没问题；但端口、路径要处理中文（显式 `encoding="utf-8"`）。
4. **编码**：所有文件读写显式 `encoding="utf-8"`；控制台输出先 `sys.stdout.reconfigure(encoding="utf-8")`。
5. **路径**：中文用户名 → 避免把临时文件放 `C:\Users\<中文>\AppData\Local\Temp` 之外的非 ASCII 路径做量化/编译。
6. **依赖**：优先纯标准库；需要 HTTP 时用 `urllib`，`requests` 可选。
7. **打包**：PyInstaller 4.x（支持 Python 3.8 且生成的 exe 可在 Win7 运行），5.x/6.x 需实测。

输出：一份「不兼容项 → 替换写法」表格 + 是否可安全在 Win7 运行的结论。
