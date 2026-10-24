# -*- coding: utf-8 -*-
"""记忆：会话历史（JSONL）+ 长期记忆（Markdown）。"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from .util import LOG, ensure_parent, read_text, write_text


class Memory(object):
    def __init__(self, home: str, session: Optional[str] = None, max_history: int = 40):
        self.home = os.path.abspath(home)
        self.session_dir = os.path.join(self.home, "sessions")
        self.long_file = os.path.join(self.home, "MEMORY.md")
        self.max_history = int(max_history)
        self.name = session or time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(self.session_dir, self.name + ".jsonl")
        self._messages: List[Dict[str, Any]] = []
        ensure_parent(self.path)

    # ── 会话 ──
    def add(self, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        record = {"role": role, "content": content, "ts": time.time()}
        if meta:
            record.update(meta)
        self._messages.append(record)
        self._append(record)
        return record

    def _append(self, record: Dict[str, Any]) -> None:
        try:
            ensure_parent(self.path)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            LOG.warning("写会话失败: %s", exc)

    def history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        n = limit or self.max_history
        return self._messages[-n:]

    def clear(self) -> None:
        self._messages = []
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except Exception:
            pass

    def save_as(self, path: str) -> str:
        ensure_parent(path)
        with open(path, "w", encoding="utf-8") as fh:
            for m in self._messages:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")
        return path

    @staticmethod
    def list_sessions(home: str) -> List[str]:
        d = os.path.join(os.path.abspath(home), "sessions")
        if not os.path.isdir(d):
            return []
        return sorted(os.listdir(d), reverse=True)

    @staticmethod
    def load(home: str, name: str) -> List[Dict[str, Any]]:
        p = os.path.join(os.path.abspath(home), "sessions", name)
        out = []
        if os.path.isfile(p):
            for line in read_text(p).splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return out

    # ── 长期记忆 ──
    def remember(self, text: str, tag: str = "note") -> str:
        ensure_parent(self.long_file)
        header = "\n## %s [%s]\n" % (time.strftime("%Y-%m-%d %H:%M"), tag)
        with open(self.long_file, "a", encoding="utf-8") as fh:
            fh.write(header + text.strip() + "\n")
        return "已写入长期记忆: %s" % self.long_file

    def recall(self, keyword: str = "", limit: int = 20) -> str:
        if not os.path.isfile(self.long_file):
            return "（长期记忆为空）"
        text = read_text(self.long_file)
        if not keyword.strip():
            return text[-4000:]
        hits = [ln for ln in text.splitlines() if keyword.lower() in ln.lower()]
        if not hits:
            return "没有匹配 '%s' 的记忆" % keyword
        return "\n".join(hits[-limit:])

    def long_term_path(self) -> str:
        return self.long_file
