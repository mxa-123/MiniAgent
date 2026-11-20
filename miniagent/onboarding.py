# -*- coding: utf-8 -*-
"""新手引导层：第一次打开就能用、看得懂、不用记命令。

约束（与主工程一致）：
- 纯标准库，零第三方依赖；
- 语法兼容 Python 3.7 / 3.8（Win7 便携包用的是 3.7.9）；
- 不用 emoji / ANSI，避免 GBK 控制台乱码；
- 设置只写用户目录 ~/.miniagent/config.json，绝不写项目目录，
  避免 API Key 被误提交进 GitHub 仓库。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .config import DEFAULT_HOME

# ── 模型来源预设：只给三个选项，避免新手一上来被一堆名词淹没 ──────────
PRESETS: List[Dict[str, Any]] = [
    {
        "id": "demo",
        "title": "先试试看",
        "subtitle": "不联网、不花钱，先熟悉界面",
        "note": "回答是模拟的，用来熟悉操作。想真正干活，请选下面两项。",
        "need_key": False,
        "config": {"provider": "mock", "model": "演示模式",
                   "api_base": "", "api_key": ""},
    },
    {
        "id": "local",
        "title": "本地免费模型",
        "subtitle": "文件不出电脑，断网也能用",
        "note": "需要先在本机装好并启动 Ollama。第一次使用会自动下载模型。",
        "need_key": False,
        "config": {"provider": "ollama", "model": "qwen2.5:7b",
                   "api_base": "http://127.0.0.1:11434", "api_key": ""},
    },
    {
        "id": "cloud",
        "title": "云端模型（效果最好）",
        "subtitle": "填一个 API Key 就能用",
        "note": "以 DeepSeek 为例，也支持其他兼容 OpenAI 接口的服务。",
        "need_key": True,
        "config": {"provider": "openai_compat", "model": "deepseek-chat",
                   "api_base": "https://api.deepseek.com/v1", "api_key": ""},
    },
]

# ── 示例任务：全部只读 / 低风险，避免新手一进来就触发写文件 ──────────
EXAMPLES: List[Dict[str, str]] = [
    {"title": "看看这个文件夹", "tag": "文件",
     "prompt": "列出当前文件夹里有哪些文件，简单说说都是干什么的"},
    {"title": "整理照片（先出计划）", "tag": "整理",
     "prompt": "看看当前文件夹里有没有图片，按月份给我一份整理计划就好，先不要真的移动文件"},
    {"title": "读一份文档", "tag": "阅读",
     "prompt": "读一下 README.md，用三句话告诉我这个项目是做什么的"},
    {"title": "联网查资料", "tag": "搜索",
     "prompt": "帮我搜索一下 Python 3.7 和 3.8 的主要区别"},
    {"title": "写个小脚本", "tag": "编程",
     "prompt": "写一个 Python 小脚本，统计当前文件夹里每种文件后缀各有多少个，先把代码给我看"},
    {"title": "记住我的偏好", "tag": "记忆",
     "prompt": "记住：我偏好用中文、简短直接的回答"},
]

# ── 工具名 → 人话 ────────────────────────────────────────────
# 值：(动作名, 模板)。模板里的 {x} 会替换成从参数里挑出的关键信息。
TOOL_FRIENDLY: Dict[str, Tuple[str, str]] = {
    "read_file":     ("读取文件", "正在读取文件 {x}"),
    "write_file":    ("写入文件", "正在写入文件 {x}"),
    "list_dir":      ("查看文件夹", "正在查看文件夹 {x}"),
    "search_files":  ("查找文件", "正在查找文件 {x}"),
    "grep_text":     ("搜索内容", "正在搜索内容 {x}"),
    "run_command":   ("执行命令", "正在执行命令 {x}"),
    "python_eval":   ("运行代码", "正在运行一段 Python 代码"),
    "fetch_url":     ("打开网页", "正在打开网页 {x}"),
    "web_search":    ("联网搜索", "正在联网搜索 {x}"),
    "remember":      ("记笔记", "正在记下：{x}"),
    "recall":        ("查笔记", "正在回想之前记下的内容 {x}"),
    "get_time":      ("看时间", "正在查看当前时间"),
    "use_skill":     ("使用技能", "正在使用技能 {x}"),
    "calc":          ("算一下", "正在计算 {x}"),
    "system_info":   ("看电脑信息", "正在查看这台电脑的信息"),
    "dir_stats":     ("统计文件夹", "正在统计文件夹 {x}"),
}

ARG_KEYS = ("path", "file", "filename", "command", "cmd", "query", "q", "url",
            "pattern", "keyword", "name", "key", "content", "text", "code",
            "directory", "dir", "skill", "expr")


def _brief(value: Any, limit: int = 60) -> str:
    s = str(value if value is not None else "").replace("\n", " ").strip()
    if len(s) > limit:
        s = s[:limit - 3] + "..."
    return s


def friendly_tool(name: str, arguments: Any = None) -> str:
    """把 `read_file({"path":"..."})` 变成「正在读取文件 xxx」。"""
    item = TOOL_FRIENDLY.get(name)
    if item is None:
        return "正在使用工具「%s」" % name
    label, tmpl = item
    hint = ""
    if isinstance(arguments, dict):
        for k in ARG_KEYS:
            v = arguments.get(k)
            if v:
                hint = _brief(v)
                break
    if "{x}" not in tmpl:
        return tmpl
    if not hint:
        return "正在" + label
    return tmpl.replace("{x}", hint)


# ── 技术报错 → 人话 + 下一步 ─────────────────────────────────
# 三条横线之后不要写 match 关键字：tests/py38_compat.py 有个宽松正则会误伤。
ERROR_RULES: List[Tuple[Any, str, str, str]] = [
    (re.compile(r"401|403|unauthorized|invalid.*api.?key|incorrect.?api.?key|authentication", re.I),
     "API Key 不对，或者还没填",
     "打开设置检查一下 Key。如果是复制来的，注意别带上多余的空格或引号。",
     "setup"),
    (re.compile(r"429|rate.?limit|quota|insufficient.?balance|余额|额度", re.I),
     "模型额度用完了，或者请求太频繁",
     "等一会儿再试；如果用的是云端服务，去服务商后台看看余额。",
     "setup"),
    (re.compile(r"404|model.?not.?found|does.?not.?exist|unknown.?model", re.I),
     "模型名字不对",
     "打开设置，把模型名改成服务商提供的准确名称。",
     "setup"),
    (re.compile(r"timed? ?out|timeout|超时", re.I),
     "模型响应太慢，超时了",
     "网络可能不太稳，再试一次；也可以在设置里换成本地模型。",
     "retry"),
    (re.compile(r"connection.?refused|10061|name.?resolution|urlerror|网络错误|getaddrinfo|refused", re.I),
     "连不上模型服务",
     "检查网络是否正常，或者模型服务有没有启动。",
     "network"),
    (re.compile(r"未配置 api_base|api_base", re.I),
     "还没设置服务地址",
     "打开设置，选一个模型来源就会自动填好。",
     "setup"),
    (re.compile(r"permission|denied|拒绝访问", re.I),
     "没有权限访问这个文件",
     "换一个文件夹试试，或者在设置里改工作目录。",
     "retry"),
    (re.compile(r"不存在工具|unknown tool", re.I),
     "模型想用一个不存在的工具",
     "这通常是模型选错了，再问一次就好。",
     "retry"),
]


def humanize_error(message: Any, provider: str = "") -> Dict[str, str]:
    """返回 {title, detail, action, raw}，前端据此显示可操作的提示。"""
    raw = str(message or "")
    prov = str(provider or "").lower()
    for pattern, title, detail, action in ERROR_RULES:
        if pattern.search(raw):
            if prov == "ollama" and action in ("network", "retry") and (
                    "连不上" in title or "超时" in title):
                title = "本机 Ollama 没连上"
                detail = "先打开 Ollama 并等它启动完成；还没装的话选「先试试看」也能熟悉界面。"
                action = "setup"
            return {"title": title, "detail": detail, "action": action, "raw": raw}
    return {
        "title": "出了点问题",
        "detail": "可以再试一次。如果一直不行，打开设置检查模型配置。",
        "action": "retry",
        "raw": raw,
    }


# ── 配置状态 ────────────────────────────────────────────────
PLACEHOLDERS = ("在这里填", "填你的", "your api key", "sk-xxxx", "your-api-key")


def config_target(cfg: Any) -> str:
    """配置落盘位置。

    Runtime 会把 rt.home 挂到 cfg.config_target 上；独立使用 onboarding 时
    回落到用户目录。这样测试 / --home 场景不会污染真实的 ~/.miniagent。
    """
    target = str(getattr(cfg, "config_target", "") or "").strip()
    return target or os.path.join(DEFAULT_HOME, "config.json")


def _blank_or_placeholder(value: Any) -> bool:
    s = str(value or "").strip()
    if not s:
        return True
    low = s.lower()
    for p in PLACEHOLDERS:
        if p in low:
            return True
    return False


def check_setup(cfg: Any) -> Dict[str, Any]:
    """前端首屏靠这个判断：要不要弹设置向导。不回显完整 API Key。"""
    provider = str(cfg.get("provider", "") or "")
    key = str(cfg.get("api_key", "") or "")
    if provider == "mock":
        configured, reason = True, "演示模式，可以直接体验界面"
    elif provider == "ollama":
        configured, reason = True, "本地模型，不需要 API Key"
    else:
        configured = not _blank_or_placeholder(key)
        reason = "已就绪" if configured else "还没设置模型，先选一个来源"
    return {
        "configured": configured,
        "reason": reason,
        "provider": provider,
        "model": str(cfg.get("model", "") or ""),
        "api_base": str(cfg.get("api_base", "") or ""),
        "api_key_set": not _blank_or_placeholder(key),
        "preset": str(cfg.get("onboarding.preset", "") or ""),
        "presets": PRESETS,
        "examples": EXAMPLES,
        "config_path": config_target(cfg),
    }


# ── 保存设置 ────────────────────────────────────────────────
ALLOWED_PROVIDERS = ("mock", "ollama", "openai_compat")
SETUP_FIELDS = ("preset", "provider", "model", "api_base", "api_key", "workspace")


def validate_setup(payload: Any) -> Tuple[bool, str]:
    """只接受白名单字段，拒绝写任意配置键。"""
    if not isinstance(payload, dict):
        return False, "设置内容格式不对"
    provider = str(payload.get("provider", "") or "").strip()
    if provider and provider not in ALLOWED_PROVIDERS:
        return False, "不认识的模型来源：%s" % provider
    base = str(payload.get("api_base", "") or "").strip()
    if base and not (base.startswith("http://") or base.startswith("https://")):
        return False, "服务地址要以 http:// 或 https:// 开头"
    model = str(payload.get("model", "") or "").strip()
    if "model" in payload and not model:
        return False, "模型名不能为空"
    key = str(payload.get("api_key", "") or "").strip()
    if key and len(key) > 500:
        return False, "API Key 太长了，请检查是不是复制错了"
    return True, ""


def apply_setup(cfg: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """把向导结果写进用户目录配置，并让调用方据此重建模型后端。"""
    ok, err = validate_setup(payload)
    if not ok:
        return {"ok": False, "message": err}

    preset = str(payload.get("preset", "") or "").strip()
    chosen = None
    for p in PRESETS:
        if p["id"] == preset:
            chosen = p
            break
    if chosen:
        for k, v in chosen["config"].items():
            # 预设里的 api_key 都是空的：用户只是改模型名时，别把已保存的 Key 冲掉
            if k == "api_key" and not v:
                continue
            cfg.set(k, v)

    # 显式字段覆盖预设（高级用户可自定义服务地址 / 模型名）
    for k in ("provider", "model", "api_base", "api_key", "workspace"):
        if k in payload:
            val = str(payload[k] or "").strip()
            if val:
                if k == "workspace":
                    val = os.path.abspath(val)
                cfg.set(k, val)

    provider = str(cfg.get("provider", "") or "")
    if provider == "openai_compat" and _blank_or_placeholder(cfg.get("api_key")):
        return {"ok": False, "message": "云端模型需要填 API Key；没有的话可以选「本地免费模型」或「先试试看」"}

    cfg.set("onboarding.done", True)
    cfg.set("onboarding.preset", preset or "custom")
    target = config_target(cfg)
    cfg.save(target)
    cfg.path = target
    return {"ok": True, "message": "设置已保存，现在可以开始聊天了",
            "path": target, "state": check_setup(cfg)}


def setup_tips(provider: str) -> str:
    if provider == "mock":
        return "演示模式不联网、不花钱，回答是模拟的。想真正干活请换一个模型来源。"
    if provider == "ollama":
        return "需要本机已安装并启动 Ollama。文件不会离开你的电脑。"
    return "API Key 只保存在你自己的用户目录里，不会发到别处，也不会写进项目文件夹。"


# ── 连接自检：填完 Key 后点一下就知道对不对 ───────────────────
def test_connection(cfg: Any, timeout: int = 5) -> Dict[str, Any]:
    provider = str(cfg.get("provider", "") or "")
    if provider == "mock":
        return {"ok": True, "message": "演示模式不需要连接，直接发消息试试吧"}
    base = str(cfg.get("api_base", "") or "").rstrip("/")
    if not base:
        return {"ok": False, "message": "还没设置服务地址，先在设置里选一个模型来源"}
    if provider == "ollama":
        url = base + "/api/tags"
        headers = {}
    else:
        url = base + "/models"
        headers = {"Authorization": "Bearer " + str(cfg.get("api_key", "") or "")}
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        try:
            resp.read(2048)
        finally:
            resp.close()
        return {"ok": True, "message": "连上了，可以开始聊天"}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            info = humanize_error("HTTP %s" % exc.code, provider)
            return {"ok": False, "message": info["title"] + "。" + info["detail"]}
        # 有些服务不提供 /models 接口，能回 HTTP 就说明网络和地址是通的
        return {"ok": True,
                "message": "服务能连上（该服务不提供模型列表），直接发消息试试"}
    except Exception as exc:
        info = humanize_error(str(exc), provider)
        return {"ok": False, "message": info["title"] + "。" + info["detail"]}
