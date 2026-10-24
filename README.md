# MiniAgent（灵枢）

一个**能在 Windows 7 / 8.1 上跑**的、可扩展的本地 AI Agent。
纯 Python 标准库实现，Python 3.8 起步，装不装第三方包都能跑。

---

## 一、为什么它能跑在 Win7

| 约束 | 结论 | 本项目的做法 |
|---|---|---|
| Python 3.9+ 安装器**拒绝**在 Win7 安装 | Win7 只能用 **Python 3.8.10**（官方最后一版支持 Win7） | 全代码兼容 3.8，有 `tests/py38_compat.py` 自动检查 |
| 老机器装包困难 / 无外网 | 依赖越少越好 | **零必需依赖**，只用 `urllib / json / subprocess`；`requests` 可选 |
| 中文用户名 + GBK 控制台 | 乱码高发 | 所有 I/O 显式 UTF-8，启动时 `sys.stdout.reconfigure(utf-8)` |
| cmd.exe 不支持 ANSI 颜色 | 彩色输出变乱码 | CLI 不输出颜色，只用纯文本标签 |
| 老浏览器 | 不能用现代前端构建产物 | Web 界面是单个原生 HTML 文件，无 CDN、无打包 |

Win8.1 同理可用（可用 Python 3.8～3.12 任意版本）。

---

## 二、三步跑起来（Windows）

```bat
install_win7.bat          :: 1. 检查 Python、装可选依赖、生成配置文件
notepad %USERPROFILE%\.miniagent\config.json   :: 2. 填 api_key
run.bat                   :: 3. 开聊（或 run_web.bat 开网页版）
```

手动方式：

```bat
python run.py --init                      :: 生成 ~/.miniagent/config.json
python run.py -p "列出当前目录的 py 文件"  :: 单次提问
python run.py                             :: 进入交互
python run.py --web                       :: 打开 http://127.0.0.1:8787
```

常用参数：`--model` `--provider` `--api-base` `--api-key` `-w 工作目录` `--session 会话名` `--no-stream` `--list-tools`。

---

## 三、目录结构

```
miniagent/
├── run.py                 入口（双击 run.bat 就是跑它）
├── install_win7.bat       环境检查 + 生成配置
├── run.bat / run_web.bat  启动脚本
├── build.bat              PyInstaller 打成单个 exe
├── config/config.example.json
├── plugins/               ★ 插件目录：丢 .py 进去就多出工具
│   └── example_tools.py   示例：calc / system_info / dir_stats
├── skills/                ★ 技能目录：丢 .md 进去就多出能力
│   ├── code_review.md
│   └── win7_compat.md
├── tests/                 冒烟测试 / 兼容检查 / 假 MCP 服务器
└── miniagent/             核心（不要改，除非你想改内核）
    ├── agent.py           ReAct 主循环
    ├── llm.py             OpenAI 兼容 / Ollama 原生 / Mock 三种后端
    ├── tools.py           工具注册表 + 自动生成 JSON Schema
    ├── builtin.py         内置工具 12 个
    ├── plugins.py         插件加载器
    ├── skills.py          技能加载器
    ├── mcp.py             MCP 客户端（stdio JSON-RPC，纯标准库）
    ├── memory.py          会话（JSONL）+ 长期记忆（Markdown）
    ├── runtime.py         装配层
    ├── cli.py             命令行
    └── webui.py           本地网页 + SSE
```

**数据流**：

```
用户输入 → Agent.chat()
              ├─ system(环境+技能目录) + 历史 + 提问 → LLM
              ├─ LLM 返回 tool_calls → Registry.execute()
              │        ├─ 内置工具 / 插件工具 / 技能工具 / MCP 工具
              │        └─ 危险工具先过确认回调
              └─ 结果回灌 → 继续，直到模型给出最终答案
```

---

## 四、模型后端

`config.json` 里 `provider` 三选一：

| provider | 适用 | 关键配置 |
|---|---|---|
| `openai_compat`（默认） | DeepSeek / OpenAI / Moonshot / 智谱 / 通义 / vLLM / Ollama 的 OpenAI 端点 | `api_base`、`api_key`、`model` |
| `ollama` | 本机 Ollama 原生接口（无需 key） | `api_base=http://127.0.0.1:11434`、`model=qwen2.5:7b` |
| `mock` | 离线自测，不联网 | 无 |

示例：

```json
{ "provider": "openai_compat", "api_base": "https://api.deepseek.com/v1",
  "api_key": "sk-xxxx", "model": "deepseek-chat" }
```

```json
{ "provider": "ollama", "api_base": "http://127.0.0.1:11434", "model": "qwen2.5:7b" }
```

> **模型不支持 function calling 怎么办**：`fallback_text_protocol` 默认开启，
> Agent 会自动改用「输出 \`\`\`json {"tool":...,"arguments":{...}}\`\`\`」的文本协议，照样能调工具。

---

## 五、四种扩展方式

### 1) 插件：加工具（推荐）

在 `plugins/` 下新建任意 `.py`：

```python
from miniagent.tools import tool

@tool(description="查询城市天气")
def weather(city: str) -> str:
    """查询天气。
    :param city: 城市名
    """
    return city + "：晴 26℃"
```

工具的参数 Schema 由**类型注解 + 文档字符串自动生成**，不用手写 JSON。
需要读配置、写记忆时用 `setup(ctx)`：

```python
def setup(ctx):                 # ctx.cfg / ctx.memory / ctx.registry / ctx.emit
    ctx.registry.register_func(my_func, risky=True)
```

`/reload` 可热重载，不用重启。

### 2) 技能：加「做事方法」

在 `skills/` 下新建 `.md`：

```markdown
---
name: 周报生成
description: 根据本周改动生成周报
---
1. 用 run_command 取 git log
2. 按「完成 / 进行中 / 风险」三段输出
3. 每条不超过 20 字
```

启动时自动进入技能目录，模型可用 `use_skill("周报生成")` 加载正文。

### 3) MCP：接别人的工具服务器

`config.json` 里加：

```json
"mcpServers": {
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    "enabled": true
  }
}
```

启动后自动连上，工具名形如 `mcp__filesystem__read_file`。
协议是 stdio + JSON-RPC 2.0，自己实现的，不依赖 `mcp` 包（Win7 也能用）。
注意：Win7 上 Node 最高只能装 **Node 16**。

### 4) 直接改内核

`miniagent/builtin.py` 加函数 + 加进注册列表即可；`agent.py` 是主循环，`llm.py` 加后端。

---

## 六、内置工具（12 个）

| 工具 | 作用 | 需确认 |
|---|---|---|
| `read_file` / `write_file` | 读写文本（UTF-8/GBK 自动兜底） | 写 |
| `list_dir` / `search_files` | 列目录 / glob 搜文件 | |
| `grep_text` | 按关键词或正则检索文件内容 | |
| `run_command` | 执行命令（拦截 format/del /f/shutdown 等） | ✅ |
| `python_eval` | 子进程执行 Python，可超时终止 | ✅ |
| `fetch_url` | 抓网页正文（去标签） | |
| `web_search` | Bing / DuckDuckGo 搜索 | |
| `remember` / `recall` | 长期记忆读写（`~/.miniagent/MEMORY.md`） | |
| `get_time` | 当前时间 | |

安全边界：

- 文件类工具限制在 `workspace` 内，路径穿越直接拒绝；
- 危险工具默认要人工确认（`/confirm off` 可关）；
- 命令有高危黑名单。

---

## 七、命令

```
/help / status / tools / skills / plugins / mcp
/model <名称>              切换模型
/config [k] [v]            查看或改配置（自动写回文件）
/new /save /sessions /load 会话管理
/reload                    热重载插件与技能
/confirm on|off            危险工具确认开关
/exit
```

---

## 八、打包成 exe（给没装 Python 的机器）

```bat
build.bat
```

Win7 目标用 **PyInstaller 4.10 + Python 3.8**（`build.bat` 里已写死这个版本）；
Win10/11 可改新版本。产物：`dist\miniagent.exe`。

---

## 九、自测

```bat
python tests/smoke_test.py     :: 18 项，不联网，Mock 后端跑通全链路
python tests/py38_compat.py    :: Python 3.8 语法/API 兼容检查
python tests/check_webui.py    :: 网页与 SSE 接口检查
```

---

## 十、已知限制

- 没有向量数据库，长期记忆是关键词检索的 Markdown（够用且轻量）。
- Web 界面不支持危险工具的交互确认（默认自动放行），需要确认请用 CLI。
- 上下文超限只做「保留最近 N 条」的朴素裁剪，没做自动摘要。
- Win7 上如需 Node 类 MCP 服务器，Node 版本 ≤ 16。

## 十一、路线图

- [ ] 上下文自动压缩 / 摘要
- [ ] 子 Agent（任务分派与并行）
- [ ] 定时任务（计划任务式自动化）
- [ ] 多模态输入（图片 → 文本）
- [ ] 更多内置技能包
