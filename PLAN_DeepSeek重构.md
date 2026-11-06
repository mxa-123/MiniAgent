# MiniAgent 重构计划：照 DeepSeek 设计 + 32 位支持

> 状态：计划已生成，未执行（用户要求先出计划、暂不动手）
> 时间：2026-11-06
> 落点：MiniAgent 便携版（`E:\AI\vm_stuff\MiniAgent_src`）

---

## 一、已确认的基线

### DeepSeek 开源实情
- **DeepSeek-V4（2026-04，MIT）**：开源了模型权重 + 代码，架构核心是
  **MoE（混合专家）+ CSA/HCA 混合注意力 + mHC 超连接 + Muon 优化器 + 可配置推理深度**。
- **DeepSeek-V4-Flash（2026-07，MIT）**：FP4/FP8 量化 + DSpark 投机解码，1M 上下文。
- **DeepSeek Harness 框架**（github.com/deepseek-ai/deepseek-harness，MIT，开发者预览 v0.1.x）：
  官方开源的 agentic 软件工程评测/智能体框架。核心思想是
  **Agent = 模型 + Harness**、**一切皆插件（Cordis 内核）**、**四档运行时模式
  （Minimal/Standard/Code/Creator）**、**append-only Trajectory 日志（可回放）**，
  含 **compaction 上下文压缩**子系统。

### MiniAgent 现状
- `miniagent/` 14 个模块：ReAct 主循环 + 3 后端 + 工具/技能/MCP/记忆 + CLI/WebUI。
- 已有 `plugins/`、`skills/` 扩展点和 Win7 x64 的 Python 3.7.9 便携包。
- 已知短板：无自动上下文压缩、无子 Agent、无调度、32 位不支持。

---

## 二、设计总纲：把 DeepSeek 的两层思想映射进 MiniAgent

### 层 1 — V4 架构思想 → 软件架构（"MoE/MLA/均衡/深度可调"的隐喻）

| V4 概念 | 映射到 MiniAgent | 对 32 位的价值 |
|---|---|---|
| **MoE 混合专家（按需激活子集）** | 能力模块化＝"专家"，按任务**懒加载**，不全量驻留 | 内存占用随任务伸缩 |
| **MLA 潜在注意力（KV 压缩 ~93%）** | **上下文压缩层**：旧轮次+工具结果压成"潜在摘要"，近期全量 | 32 位低内存不爆 |
| **无辅助损失负载均衡（动态偏置）** | **本地/云端动态路由**：按「复杂度×本地资源」决定本地跑还是上 DeepSeek-V4 API | 32 位机不硬扛大模型 |
| **MTP/投机解码（预取多步）** | **推测预取**：预测下一步工具/子步并预载 | 减少往返轮次 |
| **可配置推理深度（low/high/max）** | **四档模式 Minimal/Standard/Code/Creator** | 32 位默认 Minimal 轻量 |

### 层 2 — DeepSeek Harness 结构 → 目录/机制对齐

| Harness 子系统 | MiniAgent 对应 |
|---|---|
| Cordis 内核（插件挂/卸/依赖） | 新增 `kernel.py` 微内核 + `plugin.py` 接口 |
| model / tool / skill / session / storage / sandbox / loop / schedule / ui | 重构为对应插件域 |
| compaction 压缩 | 新增压缩层 |
| Trajectory（可回放日志） | 升级 `memory.py` 为结构化 append-only 事件流（resume/fork/search/replay） |
| 四档 runtime mode | 配置文件 `mode` 字段 |

---

## 三、目标态目录（重构后）

```
miniagent/
├── kernel.py        # Cordis 式微内核：插件装/卸/依赖解析  ← MoE 路由器
├── plugin.py        # 插件基类 + 注册表
├── model/           # llm.py + 各 provider（含 deepseek_v4）
├── tool/            # tools.py + builtin + 工具执行流水线
├── skill/           # skills.py
├── session/         # memory.py + Trajectory 日志 + compaction  ← MLA 压缩
├── router/          # 本地/云端动态路由  ← 无损失均衡
├── agent/           # agent.py（ReAct + 子Agent + plan/goal）
├── sandbox/         # 子进程/文件隔离
├── storage/         # 配置/凭据/记忆持久化
├── mode/            # Minimal/Standard/Code/Creator 预设
├── mcp/  web/  cli.py  runtime.py
```
> 现有 `plugins/`、`skills/`、`mcp.py` 用法**保持兼容**，只是挪进插件域。

---

## 四、分阶段计划

| 阶段 | 内容 | 产出 | 32 位关联 |
|---|---|---|---|
| **P0** | 调研对齐（已完成） | 本计划 | — |
| **P1** | 引入 `kernel.py`+`plugin.py`，把现有模块改挂为插件，保持兼容 | 微内核 + 插件注册 | 懒加载基础 |
| **P2** | **上下文压缩层**（MLA 映射）：旧轮次/工具结果→摘要，近期全量 | `session/compaction.py` | 核心内存优化 |
| **P3** | **本地/云端动态路由**（均衡映射）：按复杂度×资源选路 | `router/` | 32 位默认上云+本地兜底 |
| **P4** | **四档模式**（深度可调映射）：Minimal/Standard/Code/Creator | `mode/` + 配置 | Minimal=32位默认 |
| **P5** | **Trajectory 日志**（可观测性）：结构化事件流+回放 | 升级 `memory.py` | 纯文本，32 位可跑 |
| **P6** | **32 位支持**：`prepare_win7.py --arch x86` 打包 Python 3.7.9 win32 + x86 vc_redist，出 `MiniAgent-portable-win7-x86.zip`；PyInstaller onefile x86 | 32 位便携包 | 本任务落点 |
| **P7** | 自测扩展 + README 重写 + 用现有 VM 流程复测（FAT12 软盘带结果） | 测试/文档/复测报告 | 验证 x86 包 |

---

## 五、风险与缓解

- **32 位进程内存上限 ~2–3GB** → 靠 P2 压缩 + P1 懒加载 + P4 Minimal 模式，目标常驻 RAM < 1.5GB。
- **真 32 位 OS 测试** → 现有 `Win7Test.vdi` 是 x64；真 32 位需另建 32 位 VM（或至少用 x86 运行时在 x64 VM 上跑通后，标注"32 位 OS 复测"为待办）。
- **向后兼容** → 现有插件/技能/MCP 全部保留接口，P1 重点保证不破。

---

## 六、待用户拍板的两点（留底）

1. 分层映射和分阶段顺序认可吗？还是先只做 P6（单纯加 32 位）再谈重构？
2. 32 位真机验证——要不要**新建一个 32 位 Win7 VM**（用现有 VirtualBox + 同套无人值守流程）来做闭环测试？

---

## 七、相关已完成成果（上下文）

- Win7 x64 便携包已产出：`MiniAgent-portable-win7/`（Python 3.7.9 + vc_redist.x64.exe + Win7兼容说明.txt）。
- 打包链：`packaging/prepare_win7.py`、`packaging/check_win7_compat.py`、`make_portable_win7.bat`、`check_win7_compat.bat`、`README_Win7打包.md`。
- 已推送到 GitHub：`https://github.com/mxa-123/MiniAgent`（main，提交 `186d3315`）。
  - 注：本机 git 协议到 GitHub 被墙（直连 502 / gitclone 镜像 504 只读），已改用 GitHub REST API（blob→tree→commit→ref）推送。
