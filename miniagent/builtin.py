# -*- coding: utf-8 -*-
"""内置工具集：文件 / 命令 / 网络 / Python 沙箱 / 记忆 / 时间。"""

from __future__ import annotations

import fnmatch
import glob
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .tools import ToolError, tool
from .util import LOG, is_within, safe_join, truncate

BLOCKED_COMMAND_PATTERNS = [
    r"\bformat\s+[a-z]:",
    r"\bdel\s+/[fs]",
    r"\brm\s+-rf\s+/",
    r"\bshutdown\b",
    r"\btaskkill\s+/f\s+/im\s+system",
]

_UA = ("Mozilla/5.0 (Windows NT 6.1; Win64; x64) MiniAgent/0.1 "
       "(compatible; MSIE 9.0; Windows NT 6.1)")


def register_builtins(registry, ctx) -> List[str]:
    """把内置工具注册进 registry。ctx: AgentContext（提供 cfg / memory / emit）。"""
    ws = os.path.abspath(ctx.cfg.get("workspace", "."))
    memory = ctx.memory

    def _path(p: str) -> str:
        return safe_join(ws, p)

    def _guard(p: str) -> str:
        full = _path(p)
        if not is_within(ws, full):
            raise ToolError("拒绝访问工作目录之外的路径: %s（工作目录: %s）" % (full, ws))
        return full

    # ── 文件 ──────────────────────────────────────────────
    @tool(description="读取文本文件（自动按 UTF-8 / GBK 兜底）")
    def read_file(path: str, offset: int = 0, limit: int = 800) -> str:
        """读取文本文件内容。
        :param path: 文件路径，相对路径基于工作目录
        :param offset: 从第几行开始（0 为开头）
        :param limit: 最多读多少行，0 表示全部
        """
        full = _guard(path)
        if not os.path.isfile(full):
            raise ToolError("文件不存在: %s" % full)
        raw = open(full, "rb").read()
        text = None
        for enc in ("utf-8", "gbk", "utf-16", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        text = text or raw.decode("utf-8", "replace")
        lines = text.splitlines()
        if offset:
            lines = lines[int(offset):]
        if limit and limit > 0:
            lines = lines[:int(limit)]
        return "\n".join(lines)

    @tool(risky=True, description="写入文件（覆盖或追加）")
    def write_file(path: str, content: str, append: bool = False) -> str:
        """把文本写入文件，父目录自动创建。
        :param path: 目标文件路径
        :param content: 要写入的内容
        :param append: true 为追加，false 为覆盖
        """
        full = _guard(path)
        d = os.path.dirname(full)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        mode = "a" if append else "w"
        with io.open(full, mode, encoding="utf-8") as fh:
            fh.write(content)
        return "已写入 %s（%d 字符）" % (full, len(content))

    @tool(description="列出目录内容")
    def list_dir(path: str = ".", recursive: bool = False, max_entries: int = 300) -> str:
        """列出目录里的文件和子目录。
        :param path: 目录路径
        :param recursive: 是否递归
        :param max_entries: 最多返回多少条
        """
        full = _guard(path)
        if not os.path.isdir(full):
            raise ToolError("不是目录: %s" % full)
        items: List[str] = []
        if recursive:
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in dirs + files:
                    items.append(_posix(os.path.relpath(os.path.join(root, name), full)))
                    if len(items) >= max_entries:
                        break
                if len(items) >= max_entries:
                    break
        else:
            for name in sorted(os.listdir(full)):
                mark = "/" if os.path.isdir(os.path.join(full, name)) else ""
                items.append(name + mark)
        return "\n".join(items[:max_entries])

    @tool(description="按通配符查找文件，如 **/*.py")
    def search_files(pattern: str, root: str = ".", max_results: int = 100) -> str:
        """用 glob 通配符搜索文件路径。
        :param pattern: 通配符，例如 **/*.py 或 *.txt
        :param root: 搜索根目录
        :param max_results: 最多返回多少条
        """
        base = _guard(root)
        hits = glob.glob(os.path.join(base, pattern), recursive=True)
        rel = [_posix(os.path.relpath(h, base)) for h in hits]
        return "\n".join(sorted(rel)[:max_results]) or "（无匹配）"

    @tool(description="在文件里搜索文本（类 grep）")
    def grep_text(pattern: str, path: str = ".", file_glob: str = "*.*",
                  max_results: int = 50) -> str:
        """按关键词检索文件内容。
        :param pattern: 关键词或正则表达式
        :param path: 文件或目录路径
        :param file_glob: 只匹配这些文件名，如 *.py
        :param max_results: 最多返回多少条
        """
        full = _guard(path)
        try:
            rx = re.compile(pattern, re.I)
        except Exception as exc:
            raise ToolError("正则有误: %s" % exc)
        targets: List[str] = []
        if os.path.isfile(full):
            targets = [full]
        else:
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    if fnmatch.fnmatch(f, file_glob):
                        targets.append(os.path.join(root, f))
        out: List[str] = []
        for t in targets:
            try:
                raw = open(t, "rb").read()
                try:
                    text = raw.decode("utf-8")
                except Exception:
                    text = raw.decode("gbk", "replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    rel = os.path.relpath(t, full if os.path.isdir(full) else ws)
                    out.append("%s:%d:%s" % (_posix(rel), i, line.strip()[:200]))
                    if len(out) >= max_results:
                        return "\n".join(out)
        return "\n".join(out) or "（无匹配）"

    # ── 命令 ──────────────────────────────────────────────
    @tool(risky=True, description="执行系统命令（cmd/PowerShell 语法由系统决定）")
    def run_command(command: str, cwd: str = "", timeout: int = 60) -> str:
        """执行一条 shell 命令并返回输出。
        :param command: 命令字符串，例如 dir 或 python --version
        :param cwd: 工作目录，留空用默认工作目录
        :param timeout: 超时秒数
        """
        low = command.lower()
        for pat in BLOCKED_COMMAND_PATTERNS:
            if re.search(pat, low):
                raise ToolError("已拦截高危命令（命中规则 %s）" % pat)
        workdir = _guard(cwd) if cwd else ws
        try:
            proc = subprocess.run(
                command, shell=True, cwd=workdir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=max(1, int(timeout)),
            )
        except subprocess.TimeoutExpired:
            return "命令超时（%s 秒）" % timeout
        except Exception as exc:
            return "执行失败: %s: %s" % (type(exc).__name__, exc)
        out = proc.stdout.decode("utf-8", "replace") if isinstance(proc.stdout, bytes) else str(proc.stdout)
        head = "[退出码 %d]\n" % proc.returncode
        return head + truncate(out, 6000)

    # ── 网络 ──────────────────────────────────────────────
    @tool(description="抓取网页正文（去 HTML 标签）")
    def fetch_url(url: str, max_chars: int = 6000) -> str:
        """下载网页并返回纯文本。
        :param url: 以 http/https 开头的网址
        :param max_chars: 正文最多保留多少字符
        """
        if not url.lower().startswith(("http://", "https://")):
            raise ToolError("URL 必须以 http:// 或 https:// 开头")
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read(2 * 1024 * 1024)
                ctype = resp.headers.get("Content-Type", "")
        except Exception as exc:
            return "抓取失败: %s: %s" % (type(exc).__name__, exc)
        enc = "utf-8"
        m = re.search(r"charset=([\w\-]+)", ctype, re.I)
        if m:
            enc = m.group(1)
        else:
            m2 = re.search(rb'charset=["\']?([\w\-]+)', raw[:2048], re.I)
            if m2:
                enc = m2.group(1).decode("ascii", "replace")
        try:
            text = raw.decode(enc, "replace")
        except Exception:
            text = raw.decode("utf-8", "replace")
        if "<html" in text[:2000].lower() or "<body" in text[:2000].lower():
            text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
            text = re.sub(r"(?s)<[^>]+>", "\n", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r"[ \t]{2,}", " ", text)
        return truncate(text.strip(), max_chars)

    @tool(description="联网搜索（Bing/DuckDuckGo，返回标题+链接+摘要）")
    def web_search(query: str, max_results: int = 5) -> str:
        """搜索网页。
        :param query: 搜索关键词
        :param max_results: 返回条数
        """
        q = urllib.parse.quote(query)
        endpoints = [
            ("bing", "https://www.bing.com/search?q=%s&setlang=zh-CN" % q),
            ("duckduckgo", "https://html.duckduckgo.com/html/?q=%s" % q),
        ]
        last_err = ""
        for tag, url in endpoints:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _UA})
                with urllib.request.urlopen(req, timeout=25) as resp:
                    html = resp.read(1024 * 1024).decode("utf-8", "replace")
            except Exception as exc:
                last_err = "%s: %s" % (tag, exc)
                continue
            items: List[str] = []
            if tag == "bing":
                blocks = re.findall(r"(?is)<li class=\"b_algo\".*?</li>", html)
                for b in blocks:
                    t = re.search(r"(?is)<h2>.*?>(.*?)</a>", b)
                    link = re.search(r'href="(http[^"]+)"', b)
                    snip = re.search(r"(?is)<p[^>]*>(.*?)</p>", b)
                    if t:
                        items.append("- %s\n  %s\n  %s" % (
                            _strip_tags(t.group(1)),
                            link.group(1) if link else "",
                            _strip_tags(snip.group(1)) if snip else "",
                        ))
            else:
                blocks = re.findall(r"(?is)<div class=\"result[^\"]*\".*?</div>\s*</div>", html)
                for b in blocks[:20]:
                    t = re.search(r"(?is)<a[^>]*class=\"result__a\"[^>]*>(.*?)</a>", b)
                    link = re.search(r'class="result__a"[^>]*href="([^"]+)"', b)
                    snip = re.search(r"(?is)class=\"result__snippet\"[^>]*>(.*?)</a>", b)
                    if t:
                        items.append("- %s\n  %s\n  %s" % (
                            _strip_tags(t.group(1)),
                            urllib.parse.unquote(link.group(1)) if link else "",
                            _strip_tags(snip.group(1)) if snip else "",
                        ))
            if items:
                return "\n".join(items[:max_results])
        return "搜索失败（%s）。可改用 fetch_url 直接抓指定页面。" % (last_err or "无可用源")

    # ── Python 沙箱 ────────────────────────────────────────
    @tool(risky=True, description="在独立子进程里执行 Python 代码片段")
    def python_eval(code: str, timeout: int = 30) -> str:
        """执行 Python 代码并返回 stdout（子进程隔离，可超时终止）。
        :param code: Python 代码，需要输出请 print
        :param timeout: 超时秒数
        """
        tmp = ""
        try:
            fd, tmp = tempfile.mkstemp(prefix="miniagent_", suffix=".py")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(code)
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", tmp],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=max(1, int(timeout)), cwd=ws,
            )
        except subprocess.TimeoutExpired:
            return "执行超时（%s 秒）" % timeout
        except Exception as exc:
            return "执行失败: %s: %s" % (type(exc).__name__, exc)
        finally:
            if tmp and os.path.isfile(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
        out = proc.stdout.decode("utf-8", "replace")
        return "[退出码 %d]\n%s" % (proc.returncode, truncate(out, 6000))

    # ── 记忆 / 环境 ────────────────────────────────────────
    @tool(description="写入长期记忆（跨会话保留）")
    def remember(text: str, tag: str = "note") -> str:
        """把重要信息写入长期记忆文件。
        :param text: 要记住的内容
        :param tag: 分类标签
        """
        return memory.remember(text, tag)

    @tool(description="检索长期记忆")
    def recall(keyword: str = "") -> str:
        """按关键词检索长期记忆，留空返回最近内容。
        :param keyword: 关键词
        """
        return memory.recall(keyword)

    @tool(description="获取当前日期时间")
    def get_time() -> str:
        """返回当前系统时间和星期。"""
        return time.strftime("%Y-%m-%d %H:%M:%S %A", time.localtime())

    registered: List[str] = []
    for fn in (read_file, write_file, list_dir, search_files, grep_text,
               run_command, fetch_url, web_search, python_eval,
               remember, recall, get_time):
        t = registry.register_func(fn, source="builtin")
        registered.append(t.name)
    LOG.debug("内置工具注册完成: %s", registered)
    return registered


def _posix(p: str) -> str:
    """Windows 路径统一成 / 分隔，模型更好理解。"""
    return p.replace("\\", "/")


def _strip_tags(s: str) -> str:
    s = re.sub(r"(?s)<[^>]+>", "", s or "")
    return (s.replace("&amp;", "&").replace("&quot;", '"')
             .replace("&#39;", "'").replace("&nbsp;", " ").strip())
