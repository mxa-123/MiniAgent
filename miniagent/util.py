# -*- coding: utf-8 -*-
"""通用工具函数：编码、日志、路径安全、文本截断。"""

from __future__ import annotations

import io
import logging
import os
import sys
import time
from typing import Any, Optional

LOG = logging.getLogger("miniagent")


def setup_console() -> None:
    """Windows 7 中文控制台默认是 GBK，强制切成 UTF-8，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            try:
                if hasattr(stream, "buffer"):
                    setattr(stream, "_miniagent_wrapped", True)
            except Exception:
                pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    fmt = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
    logging.basicConfig(level=getattr(logging, str(level).upper(), logging.INFO), format=fmt)
    if log_file:
        try:
            ensure_parent(log_file)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter(fmt))
            logging.getLogger().addHandler(fh)
        except Exception as exc:  # 日志失败不能影响主流程
            LOG.debug("无法写日志文件 %s: %s", log_file, exc)


def ensure_parent(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def read_text(path: str, encoding: str = "utf-8") -> str:
    with io.open(path, "r", encoding=encoding, errors="replace") as fh:
        return fh.read()


def write_text(path: str, content: str, encoding: str = "utf-8") -> None:
    ensure_parent(path)
    with io.open(path, "w", encoding=encoding, errors="replace") as fh:
        fh.write(content)


def safe_join(workspace: str, path: str) -> str:
    """把相对路径解析到 workspace 内；绝对路径原样返回（由工具层再判白名单）。"""
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(os.path.abspath(workspace), path))


def is_within(workspace: str, path: str) -> bool:
    try:
        root = os.path.abspath(workspace)
        full = os.path.abspath(path)
        return os.path.commonpath([root, full]) == root
    except Exception:
        return False


def truncate(text: Any, limit: int = 8000, head: bool = True) -> str:
    s = text if isinstance(text, str) else repr(text)
    if limit and len(s) > limit:
        note = "\n...[已截断 %d 字符]" % (len(s) - limit)
        return (s[:limit] + note) if head else (note + s[-limit:])
    return s


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def short(value: Any, limit: int = 160) -> str:
    return truncate(value, limit).replace("\n", " ")
