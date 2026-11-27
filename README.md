# MiniAgent（灵枢）

**一个会自己干活的 AI 助手。** 你说一句「把桌面这些照片按月份整理好」，它会自己拆步骤、动手做、看结果，不对就换个办法，直到把事办完。

它和聊天 AI 的区别只有一句话：**聊天 AI 给你答案，它帮你把活干完。**

- 有软件窗口：双击 `run.bat` 直接开一个桌面窗口，不用开浏览器、不用记命令
- 有安装包：`dist/MiniAgent-安装包.exe` 双击就装，不用管理员权限、不用先装 Python
- 多个模型随时切换：云端、本地 Ollama、离线演示都存进同一个「模型目录」，窗口顶上一拉就换，不用改配置文件
- 四档模式：极简 / 标准 / 编程 / 创作，按任务挑一档，自动调整步数和提示词
- 本地优先：文件、对话都留在你自己的电脑里，断网也能用
- 全免费、全开源：[github.com/mxa-123/MiniAgent](https://github.com/mxa-123/MiniAgent)
- 老电脑：源码方式仍可在 Windows 7 / 8.1 上跑（见下面「Windows 7 说明」）

---

## 一、最快上手：双击两个文件

### 方式 A：直接用（项目文件夹里）

**双击 `run.bat`** → 弹出「MiniAgent」桌面窗口。第一次打开会自动问你选哪个模型来源，选完点「保存并开始」就能聊天。

窗口从上到下就三块：最上面是「模型」和「模式」两个下拉框加「设置」按钮，中间是聊天记录，下面输入框打字后按 **Enter 发送**、**Shift+Enter 换行**。两个下拉都是即选即生效，不用重启。

> 窗口没出来？双击 `run_debug.bat`，黑框会把错误留着不关；详细记录也在 `~/.miniagent/desktop.log`。

### 方式 B：装到电脑里（推荐给不想折腾的人）

**双击 `dist/MiniAgent-安装包.exe`** → 一路点「下一步」→ 装好。

- 装在 `C:\Users\你的用户名\AppData\Local\MiniAgent`，**不弹管理员权限窗口**
- 自动建好桌面快捷方式「MiniAgent」和开始菜单文件夹
- 不用先装 Python，安装包里已经自带
- 不想要了：开始菜单 → MiniAgent → Uninstall，或到「设置 → 应用」里卸载
- 你的设置存在 `~/.miniagent/config.json`，**卸载不会删掉它**

> 安装包只是文件，构建时只做了编译和完整性检查，没有真的装到任何电脑上。

### 第一次打开：选一个模型来源

| 选哪个 | 适合谁 | 要准备什么 |
|---|---|---|
| **先试试看** | 只想看看界面长什么样 | 什么都不用。回答是模拟的 |
| **本地免费模型** | 在意隐私、想断网用 | 本机装好并启动 Ollama |
| **云端模型（效果最好）** | 想真正拿它干活 | 一个 API Key（以 DeepSeek 为例，填进去就行） |

选完点「保存并开始」立刻生效，不用重启。拿不准可以填完 Key 先点「测试连接」，会直接告诉你连没连上。不想选就点「跳过，先用演示模式」。

界面上有一排「不知道说什么？点一个试试」，六个卡片点一下就发送。或者直接用自己的话说，比如「读一下 README.md，用三句话讲清楚」。

---

## 二、常见问题

**没有 API Key 怎么办？**
选「本地免费模型」（装 Ollama）或「先试试看」。云端 Key 需要去模型服务商官网申请。

**报错看不懂？**
窗口会把技术报错翻译成人话，还会写清楚下一步，配一个「去设置」按钮。比如「API Key 不对 → 去设置检查 Key」。

**它会动我别的地方的文件吗？**
默认只能在**软件所在文件夹**里操作。写文件、执行命令、跑代码这三类操作，会先弹窗问你「允许 / 拒绝」，**90 秒不点就自动拒绝**，不点绝不会偷偷执行。重要文件仍然建议先备份。

**设置存在哪？安全吗？**
存在你自己的用户目录 `~/.miniagent/config.json`，**不会写进项目文件夹**，也不会被提交到 GitHub。API Key 输入框是星号，而且不会回显完整值。

**想换模型？**
窗口顶上「模型」下拉直接选，立刻生效；网页版和命令行也各有对应的切换入口。想加一条新模型，点「设置」里新增，或命令行用 `/addmodel`。已经存过 Key 的话，Key 留空就表示不修改，只改模型名不会丢 Key。

**四档模式是干嘛的？**
「极简」省步骤省算力，适合简单问答；「标准」是默认；「编程」和「创作」给更多步骤和更专门的提示词。切换同样即选即生效。

**想用网页版或命令行？**
`run_web.bat` 开浏览器界面，`run_cli.bat` 开命令行。两者都保留着，功能没变。

**Windows 7 能用这个安装包吗？不能。**
本机的 Python 是 3.14 64 位，PyInstaller 6.x 打出来的程序**只支持 64 位 Windows 8 / 10 / 11**，不支持 Win7，也不支持 32 位系统。Win7 请按下面的「Windows 7 说明」用源码方式跑。

---

## 三、Windows 7 说明（重要）

### 有专门的 32 位安装包

**`dist/MiniAgent-Win7-32位安装包.exe`** —— 一个包通吃 Win7 / Win8.1 的 32 位和 64 位系统。

| 项 | 值 |
|---|---|
| 大小 | 约 20 MB |
| PE 位数 | `0x014c`，真 32 位（32 位程序在 64 位系统上照样跑） |
| 内置运行时 | Python 3.7.9 win32 + tkinter 8.6，**目标机不需要装 Python** |
| 安装位置 | `C:\Users\你的用户名\AppData\Local\MiniAgent` |
| 权限 | HKCU，`RequestExecutionLevel user`，**不弹管理员窗口** |
| 桌面快捷方式 | `MiniAgent`（图形界面）+ 开始菜单里 `MiniAgent-CLI`（控制台） |
| 卸载 | 开始菜单 → MiniAgent → Uninstall |

> **为什么必须用 Python 3.7.9 而不是 3.8**：Python 3.8 在裸 Win7 SP1 上依赖 `KB2533623`（微软已下线该补丁），`import ssl` 必然失败；3.7 走老式 `LoadLibrary`，不需要这个补丁。`packaging/README_Win7打包.md` 记着这条铁律。

### 其他情况

| 情况 | 怎么做 |
|---|---|
| Win7 / Win8.1（任意位数） | 直接用 `dist/MiniAgent-Win7-32位安装包.exe` |
| Win10 / Win11 64 位 | 用 `dist/MiniAgent-Win7-32位安装包.exe` 也行；`dist/MiniAgent-安装包.exe` 是 64 位专用版 |
| 想跑源码 | 源码只用标准库，兼容 Python 3.7 / 3.8，双击 `run.bat` |

### Win7 上的四个功能入口

| 功能 | 怎么用 |
|---|---|
| **开机自启** | 窗口左下角「开机自启：关」点一下变成「开」。写 `HKCU\...\CurrentVersion\Run`（Win7 上写启动文件夹脚本会被安全策略拦，注册表 Run 键是唯一可靠路径） |
| **无人值守执行** | `MiniAgent-CLI.bat -p "把 D:\notes 汇总成 md" -y`。`-y` 会自动批准工具调用，不再等人输入，适合挂计划任务 |
| **多会话** | 左栏「新建对话」，历史会话点一下就切回，消息各自隔离存储 |
| **插件面板** | 左栏「插件」看已加载插件和工具，放 `.py` 进 `plugins/` 就能扩展，面板里可「重新加载插件」 |

---

## 四、它能替你干什么

| 场景 | 你可以这样说 |
|---|---|
| 整理文件 | 「把当前文件夹里的图片按月份归类，先给我一份计划」 |
| 查资料 | 「帮我搜索一下 Python 3.7 和 3.8 的主要区别」 |
| 读文档 | 「读一下 README.md，三句话讲清楚」 |
| 批量改内容 | 「把这些文件里的旧称呼统一换成新的」 |
| 写代码 | 「写个脚本统计每种后缀各有多少文件，先把代码给我看」 |
| 记事 | 「记住：我偏好中文、简短直接的回答」 |

内置 12 个工具：读写文件、列目录、搜文件、搜内容、执行命令、跑 Python、抓网页、联网搜索、长期记忆、看时间。工具调用在窗口里显示成人话（比如「正在读取文件 README.md」），不会甩一堆看不懂的 JSON 给你。

---

## 五、接下来做什么（迭代顺序）

已完成：修好所有 bat 的启动目录 Bug、加上桌面窗口、做出可双击的安装包，并把内核换成插件化架构——**模型从「一个配置」变成「一个目录」**，加了四档运行时模式。架构细节见下面第六节。

下一轮（对新手有直接感知）：
- 长对话自动压缩，聊久了不卡、不爆内存
- 结构化步骤记录，能回看「它刚才到底做了什么」

更后面（决定上限）：本地 / 云端自动路由、可回放的 Trajectory 日志、按槽位贡献界面的正式插件包。完整分层与阶段见 [PLAN_DeepSeek重构.md](PLAN_DeepSeek重构.md)。

---

## 六、技术说明（进阶，新手可跳过）

### 插件化内核：这一轮改了什么

以前模型是配置里四个写死的标量，加能力就得改主循环。现在换成「内核 + 可插拔部件」：

| 部件 | 文件 | 作用 |
|---|---|---|
| 微内核 | `kernel.py` | 服务定位 `provide/get/require`、可拦截事件链 `on/emit`、可卸载副作用 `effect/inject`、槽位 `slot/contributions`、分段提示词 `section/compose_prompt`、插件 `load/unload/dispose` |
| 模型目录 | `models.py` | 多条模型 + 当前生效模型，切换时重建 LLM 后端 |
| 运行时模式 | `mode.py` | 四档模式，影响步数与提示词段 |
| 装配中心 | `runtime.py` | 把上面几样接起来，给三个界面提供统一入口 |

一次提问经过的路径：`agent.chat()` 先发 `agent.request` 事件，插件可以改写本轮用的 `llm`（**只改本轮，不动全局**）或短路；系统提示词由 `compose_prompt()` 把 `persona` 段和各模式段拼起来；模型由 `ModelRegistry.resolve()` 给出只读视图传给 `create_llm`。所有注册都返回 `Disposer`，卸载时逐项回滚，不留残留。

这样带来的实际好处：加一种模型来源、加一段行为约束、加一个界面区块，都不必再动 ReAct 主循环。

### 启动入口

```
run.bat         默认：pythonw.exe desktop.py（桌面窗口，无黑框）
run_debug.bat   带控制台启动桌面窗口，排错用
run_web.bat     浏览器界面（保留）
run_cli.bat     命令行界面（保留）
install_win7.bat  Win7 / 8.1 环境检查
build.bat       旧版 PyInstaller 打 CLI 的脚本
installer/build_installer.bat   一键生成安装包
```

每个 bat 都在调用 python 之前做了 `cd /d "%~dp0"`，从任何目录（包括 `C:\Windows\System32`）双击都能找到自己的文件。bat 内容保持纯 ASCII，避免 Win7 GBK 控制台中文乱码。`run.bat` 还会逐个检查 PATH 里的 Python，挑一个真的带 tkinter 的来开窗口。

### 安装包怎么来的

`installer/build_installer.py` 先用 PyInstaller 把 `desktop.py` 打成自带 Python 的 `MiniAgent.exe`（`--onefile --windowed --add-data` 带上 config / skills / plugins），再调 `C:\Program Files (x86)\NSIS\makensis.exe` 编译 `installer/MiniAgent.nsi`，成品放 `dist/`。

- 如果 PyInstaller 和本机 Python 不兼容，脚本会自动降级：改成安装源码 + 检测系统 Python + 快捷方式指向 `pythonw.exe desktop.py`，并明确提示「需已安装 Python 3.8+」
- NSIS 只写 HKCU 卸载信息、装到 `%LOCALAPPDATA%\MiniAgent`，不写 HKLM、不弹 UAC
- 构建中间物（build/、*.spec、__pycache__）用完清理；**不会执行生成的安装程序**

### 桌面窗口的设计

`desktop.py` 只用 tkinter 标准库：对话在后台线程跑，事件经队列交给主线程用 `after` 刷新；危险操作确认用 `threading.Event` 把请求交给主线程弹窗，默认拒绝、90 秒超时拒绝；`pythonw.exe` 没有控制台，所以异常一律写 `~/.miniagent/desktop.log` 并弹窗。

桌面版一律逐条确认危险操作，即使配置里写过 `auto_confirm=true` 也不静默放行。

打包成 exe 后 `__file__` 会指向临时解压目录，所以启动时按 `sys.executable` 把工作目录切回 exe 所在目录，扩展目录也指向安装文件夹，否则 config / skills / plugins 会找不到。

设置只走 `apply_setup()` 写用户目录，保存后按 WebUI 的同样做法同步进模型目录并重建模型后端。模型 / 模式下拉则直接走 `Runtime` 的统一入口。

### 为什么源码能跑在 Win7

| 约束 | 做法 |
|---|---|
| Python 3.9+ 安装器拒绝在 Win7 安装 | 全代码兼容 3.8；Win7 便携包用 Python 3.7.9 |
| 中文用户名 + GBK 控制台 | 所有 I/O 显式 UTF-8；CLI / bat 不输出 ANSI 颜色与 emoji |
| 老机器装包困难 / 无外网 | 零必需依赖，只用标准库；`requests` 可选 |

Win7 打包链在 `packaging/`：`prepare_win7.py`、`check_win7_compat.py` 等。

### 目录结构

```
desktop.py              桌面窗口（默认入口，含模型 / 模式下拉）
run.py / miniagent/cli.py        命令行入口
miniagent/webui.py      浏览器界面（含模型 / 模式接口）
miniagent/kernel.py     插件化微内核：服务定位 / 事件链 / 槽位 / 分段提示词
miniagent/models.py     模型目录 + 多模型切换（兼容旧单模型配置）
miniagent/mode.py       四档运行时模式
miniagent/onboarding.py 设置向导 / 人话层 / 连接自检
miniagent/agent.py      ReAct 主循环
miniagent/llm.py        OpenAI 兼容 / Ollama 原生 / Mock 三种后端
miniagent/tools.py / builtin.py  工具注册表 + 12 个内置工具
miniagent/config.py / runtime.py 配置与运行时装配
miniagent/db.py         SQLite：会话 / 消息 / 执行轨迹三张表
miniagent/autostart.py   开机自启（HKCU Run 键，Win7 唯一可靠路径）
config/config.example.json
plugins/  skills/       丢文件进去就多出工具 / 能力
installer/              NSIS 脚本 + 构建脚本 + 源码模式启动器
dist/                   最终安装包（Win8+64 位版 + Win7/32 位版）
```

### 模型后端与模型目录

`provider` 三选一：`openai_compat`（DeepSeek / OpenAI / 智谱 / 通义 / vLLM / Ollama 的 OpenAI 端点）、`ollama`（本机原生接口，无需 Key）、`mock`（离线演示）。

> 模型不支持 function calling 时，`fallback_text_protocol` 会自动降级成「输出 JSON 代码块」的文本协议，照样能调工具。

新配置用 `models: [ ... ]` 存多条模型、`active_model` 指定当前用哪条：

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识，只允许字母数字 / 点 / 短横 / 下划线 |
| `label` | 界面上显示的名字 |
| `provider` / `model` / `api_base` / `api_key` | 一条模型自己的连接信息 |
| `enabled` | 是否参与切换 |

**兼容旧配置**：没有 `models` 时，注册表会把顶层那四个标量自动包装成一条 `id="default"` 的模型，行为跟以前完全一样。切换模型时顶层四个标量会同步刷新，所以 `--model`、环境变量、老代码路径都不用改。目录对外只输出 `has_key`，**不回显 API Key 明文**。写盘位置跟着 `Runtime.home` 走，测试与自定义 `--home` 不会碰到用户真实配置。

`mode.py` 的四档模式作用于 `max_steps` 和系统提示词分段：`minimal`(6 步) / `standard`(24 步) / `code`(32 步) / `creator`(40 步)。模式段落通过内核的 `section()` 注入，卸载时一并移除。

### 命令行参数与斜杠命令

```bat
python run.py --init                      :: 生成默认配置
python run.py -p "列出当前目录的 py 文件"  :: 单次提问
python run.py --web                       :: 网页界面
python run.py --list-tools                :: 打印工具清单
```

常用参数：`--model` `--provider` `--api-base` `--api-key` `-w 工作目录` `--session` `--no-stream` `-y`。

`-y`（无人值守）会**自动批准所有工具调用**，不再等人工输入，配合 `-p` 就是一条命令跑完一个任务，适合挂 Windows 计划任务。

斜杠命令：`/help /status /tools /skills /plugins /mcp /model /config /new /save /sessions /load /reload /confirm /exit`。

本轮新增：`/models`（列出模型目录，★ 标记当前）、`/use <id>`（切换）、`/addmodel <id> <来源> <模型名> [地址]`（新增）、`/mode [名称]`（查看或切换四档模式）、`/kernel`（查看内核里的服务 / 提示词段 / 槽位）。网页版对应接口是 `/api/models`、`/api/modes`、`/api/kernel`。

### 数据存在哪

| 内容 | 位置 |
|---|---|
| 会话与消息 | `~/.miniagent/miniagent.db`（SQLite，三张表：`sessions` / `messages` / `trajectory`） |
| 执行轨迹 | 同上库的 `trajectory` 表，逐条记 `thought` / `plan` / `action` / `observation` / `final` |
| 配置 | `~/.miniagent/config.json` |
| 日志 | `~/.miniagent/desktop.log` |

数据库路径刻意避开中文用户名目录，Win7 上不会出现编码问题。

### 自测

```bat
python -m py_compile desktop.py installer\build_installer.py
python tests/smoke_test.py        :: 18 项，不联网，Mock 后端跑通全链路
python tests/py38_compat.py       :: Python 3.8 语法/API 兼容检查
python tests/check_webui.py       :: 网页、状态接口、设置接口、SSE 对话流
python tests/test_onboarding.py   :: 新手引导层
python tests/test_kernel.py       :: 微内核 / 模型目录 / 四档模式
python tests/vm_test_kernel.py    :: Win7 虚拟机内的内核逻辑自检（写软盘回传结果）
installer\build_installer.bat     :: 编译安装包并列出 dist 内容
```

### 已知限制

- `dist/MiniAgent-安装包.exe` 是 **64 位 Win8+/Win10/Win11 专用**；Win7 和 32 位系统请用 `dist/MiniAgent-Win7-32位安装包.exe`。
- 长期记忆是关键词检索的 Markdown，没有向量数据库。
- 上下文超限只做「保留最近 N 条」的朴素裁剪，还没做自动摘要（下一轮）。
- 插件面板只做「加载 / 卸载 / 列工具」，插件热替换（运行中替换实现）还没做。
- Win7 上 Node 类 MCP 服务器需 Node ≤ 16。
- 插件化内核目前只提供机制（服务 / 事件 / 槽位 / 分段提示词），**还没有做成可分发的插件包格式**，也没有实现自动路由与 Trajectory 日志。

---

## 七、设计灵感与版权说明

本项目在架构上参考了开源项目 **DeepSeek Harness** 公开的设计思想：插件化内核、服务定位、事件拦截、把模型当作可插拔目录、分段系统提示词、多档运行时模式。

需要明确几点：

- **只借鉴架构思想**。`kernel.py` / `models.py` / `mode.py` 及所有接线代码均为从零独立编写，仅用 Python 标准库；未使用、未复制、未翻译任何第三方项目的源码、注释、常量、配置键名、UI 文案、图标与素材。
- **不冒用名称**。MiniAgent（灵枢）与 DeepSeek / DeepSeek Harness 没有官方关联，也不是其分支或衍生版本；文档提到对方仅用于如实说明设计灵感来源。
- **参考资料不入库**。本机上仅用于阅读理解的其他项目源码，没有被复制进本仓库，也不会被打进安装包。
- **第三方组件**：运行时可选依赖 Ollama 及各类 OpenAI 兼容接口服务，打包用到 PyInstaller / NSIS；它们各自遵循自己的许可证，本项目不重新分发它们的源码。
- **本项目自身许可**：见 [`packaging/LICENSE.txt`](packaging/LICENSE.txt)（自由用于学习、研究与个人用途，复制 / 修改 / 分发需保留该声明）。参考项目的许可证以其自身仓库声明为准，本项目不作断言。

> 若相关权利方认为本项目的表述或实现有不妥，欢迎提 issue，我们会及时调整。
