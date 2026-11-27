# -*- coding: utf-8 -*-
"""会话持久化（SQLite）：Win7 / Python 3.7 兼容，零第三方依赖。

数据放在 ~/.miniagent/miniagent.db，与配置、日志同目录。
任何异常都吞掉并返回安全默认值，绝不因为数据库问题让界面起不来。
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


def db_path() -> str:
    home = os.path.join(os.path.expanduser("~"), ".miniagent")
    try:
        if not os.path.isdir(home):
            os.makedirs(home)
    except Exception:
        pass
    return os.path.join(home, "miniagent.db")


def _connect() -> Any:
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> bool:
    try:
        conn = _connect()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT DEFAULT '', "
            "created_at REAL, updated_at REAL)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
            "role TEXT NOT NULL, content TEXT NOT NULL, ts REAL)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_sid ON messages(session_id, id)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS trajectory ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
            "kind TEXT NOT NULL, detail TEXT NOT NULL, ts REAL)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traj_sid ON trajectory(session_id, id)")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def list_sessions(limit: int = 60) -> List[Dict[str, Any]]:
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT id, title, model, updated_at FROM sessions "
                    "ORDER BY updated_at DESC LIMIT ?", (int(limit),))
        rows = cur.fetchall()
        conn.close()
        return [{"id": r[0], "title": r[1] or "新的对话",
                 "model": r[2] or "", "updated_at": r[3] or 0} for r in rows]
    except Exception:
        return []


def create_session(title: str = "新的对话", model: str = "") -> Optional[str]:
    sid = str(uuid.uuid4())
    now = time.time()
    try:
        conn = _connect()
        conn.execute("INSERT INTO sessions (id, title, model, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?)", (sid, title or "新的对话", model or "", now, now))
        conn.commit()
        conn.close()
        return sid
    except Exception:
        return None


def rename_session(sid: str, title: str) -> None:
    try:
        conn = _connect()
        conn.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?",
                     ((title or "")[:80], time.time(), sid))
        conn.commit()
        conn.close()
    except Exception:
        pass


def touch_session(sid: str) -> None:
    try:
        conn = _connect()
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), sid))
        conn.commit()
        conn.close()
    except Exception:
        pass


def delete_session(sid: str) -> None:
    try:
        conn = _connect()
        conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def add_message(sid: str, role: str, content: str) -> None:
    try:
        conn = _connect()
        conn.execute("INSERT INTO messages (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
                     (sid, str(role), str(content or ""), time.time()))
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), sid))
        conn.commit()
        conn.close()
    except Exception:
        pass


def list_messages(sid: str) -> List[Dict[str, str]]:
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id ASC",
                    (sid,))
        rows = cur.fetchall()
        conn.close()
        return [{"role": r[0], "content": r[1]} for r in rows]
    except Exception:
        return []


def clear_messages(sid: str) -> None:
    try:
        conn = _connect()
        conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), sid))
        conn.commit()
        conn.close()
    except Exception:
        pass


def add_trace(sid: str, kind: str, detail: str) -> None:
    """记录一条 Agent 轨迹（thought / tool_call / tool_result / final）。"""
    try:
        conn = _connect()
        conn.execute("INSERT INTO trajectory (session_id, kind, detail, ts) "
                     "VALUES (?, ?, ?, ?)", (sid, str(kind), str(detail or ""), time.time()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def list_trace(sid: str, limit: int = 200) -> List[Dict[str, str]]:
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT kind, detail FROM trajectory WHERE session_id=? "
                    "ORDER BY id DESC LIMIT ?", (sid, int(limit)))
        rows = cur.fetchall()
        conn.close()
        return [{"kind": r[0], "detail": r[1]} for r in reversed(rows)]
    except Exception:
        return []


def clear_trace(sid: str) -> None:
    try:
        conn = _connect()
        conn.execute("DELETE FROM trajectory WHERE session_id=?", (sid,))
        conn.commit()
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    print("db:", db_path(), "init:", init_db())
