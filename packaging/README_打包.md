# MiniAgent 打包与分发

把 MiniAgent（灵枢）做成可在其它电脑（含 Windows 7 / 8.1）安装的软件包。
**核心思路：安装包自带 Python 3.8 嵌入式运行时，目标机无需预装任何东西。**

---

## 目录里有什么

| 文件 | 作用 |
|---|---|
| `prepare.py` | 下载并解压嵌入式 Python 3.8、暂存应用文件、可选生成便携版 |
| `MiniAgent.nsi` | NSIS 安装脚本（生成正式 `.exe` 安装包） |
| `build_installer.bat` | 一键生成安装包 `dist\MiniAgent-Setup.exe` |
| `make_portable.bat` | 生成便携版 `dist\MiniAgent-portable.zip`（解压即用，无需 NSIS） |
| `download_runtime.bat` | 仅下载 Python 3.8 运行时 |
| `make_icon.py` | 生成程序图标 `assets\miniagent.ico` |
| `LICENSE.txt` | 许可说明 |

---

## 方案 A：正式安装包（推荐给"其它电脑"）

适合分发给别人——双击 `MiniAgent-Setup.exe` 即可安装，自动建开始菜单/桌面快捷方式，带卸载程序。

### 你需要做的（在自己电脑上，一次）

1. 装 NSIS（免费）：<https://nsis.sourceforge.io/Download>  （勾选加入 PATH）
2. 确保能联网（首次要下载 Python 3.8 运行时，约 7.8 MB）
3. 双击 `build_installer.bat`
4. 等待出现 `dist\MiniAgent-Setup.exe`

### 在其它电脑上

双击 `MiniAgent-Setup.exe` → 选安装位置（默认 `%LOCALAPPDATA%\Programs\MiniAgent`，**不需要管理员权限**）→ 安装完成勾选"启动网页版"即可。
开始菜单里有：
- **MiniAgent 命令行** —— 黑框 REPL，输入 `/help` 看命令
- **MiniAgent 网页版** —— 本地网页界面（自动开浏览器）

首次运行会生成配置文件：`%USERPROFILE%\.miniagent\config.json`，把 `api_key` / `api_base` / `model` 填好就能用了。

---

## 方案 B：便携版 ZIP（最省事，验证最快）

不想装 NSIS？直接用便携版：

1. 双击 `make_portable.bat`
2. 得到 `dist\MiniAgent-portable.zip`
3. 拷到任何电脑，解压，双击 **`MiniAgent-网页版.bat`** 即可

便携版和安装版用的是同一套运行时，零依赖、可放 U 盘随身走。

---

## 架构要点（为什么能在 Win7 跑）

- **运行时**：捆绑 `python-3.8.10-embed-amd64.zip`（官方嵌入式发行版）。
  Python 3.9+ 的安装器会拒绝在 Win7 上装，3.8 是官方支持 Win7 的最后一版。
- **应用**：MiniAgent 本体只用 Python 标准库（HTTP 用 urllib、界面用 http.server），
  所以嵌进去的 3.8 运行时无需任何额外包即可运行。
- **启动**：快捷方式指向 `python\python.exe run.py`（命令行）或 `python\pythonw.exe run.py --web`（网页版，无黑框）。
  `run.py` 会自动把自己所在目录加入 `sys.path`，因此 `import miniagent` 永远成功。
- **32 位系统**：极少数老机器是 32 位。把 `prepare.py` 里的 arch 改成 `win32` 重新打包即可
  （对应 `python-3.8.10-embed-win32.zip`）。

---

## 常见问题

- **Q：目标机完全没网能装吗？**
  A：能。"下载运行时"只需**打包者**联网一次；生成的安装包/便携包里已经包含了 Python，目标机离线也能跑。
  只有 Agent 真正调用大模型 API 时才需要联网。

- **Q：安装包多大？**
  A：约 8~9 MB（Python 运行时占大头，应用本身几百 KB）。

- **Q：安装后怎么更新？**
  A：重新跑 `build_installer.bat` 生成新包，覆盖安装即可；用户数据在 `%USERPROFILE%\.miniagent`，不会被清掉。

- **Q：想换成自己的模型/API？**
  A：装好后编辑 `%USERPROFILE%\.miniagent\config.json`，
  参考项目根目录 `config\config.example.json`（DeepSeek / OpenAI / Moonshot / 本地 Ollama / vLLM 都支持）。

---

## 复用现有代码

- 生成图标：`python make_icon.py`
- 只下运行时：`python prepare.py --runtime-only`
- 改 32 位：`python prepare.py --arch win32 --portable`
