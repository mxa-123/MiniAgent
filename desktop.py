# -*- coding: utf-8 -*-
"""MiniAgent 桌面窗口（默认界面）。

用 tkinter 标准库实现，零第三方依赖，语法兼容 Python 3.7 / 3.8。

设计要点：
1. 对话在后台线程跑，worker 只往 queue 里丢事件，主线程用 after 轮询刷新，界面不卡；
2. 危险工具的确认在工作线程发起，用 threading.Event + 队列交给主线程弹窗，
   默认拒绝、90 秒超时自动拒绝，绝不静默放行；
3. pythonw.exe 没有 stdout/stderr，所有异常写 ~/.miniagent/desktop.log 并弹窗提示；
4. PyInstaller 冻结后 __file__ 指向临时解压目录，启动时把工作目录切到 exe 所在目录，
   否则 config / skills / plugins 这些相对路径会找不到；
5. 绝不调用 cfg.save()（无参保存会写进项目目录），设置一律走 apply_setup()。
"""

from __future__ import annotations

import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

# 与 run.py 保持一致：允许用绝对路径 / 从别的工作目录启动 desktop.py
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

# 便携版 Python 3.7 自带 tcl/tk 库在 python/tcl/ 下。必须在 import tkinter 之前
# 显式指路，否则 Win7 上 Tk 可能找不到脚本库导致 import 失败 → 误降级到 WebUI。
try:
    if sys.version_info < (3, 8):
        _py_dir = os.path.dirname(os.path.abspath(sys.executable))
        for _tcl in (os.path.join(_py_dir, "tcl"),
                     os.path.join(os.path.dirname(_py_dir), "tcl"),
                     os.path.join(_PROJECT_DIR, "tcl")):
            if os.path.isdir(os.path.join(_tcl, "tcl8.6")):
                os.environ.setdefault("TCL_LIBRARY", os.path.join(_tcl, "tcl8.6"))
                os.environ.setdefault("TK_LIBRARY", os.path.join(_tcl, "tk8.6"))
                break
except Exception:
    pass

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:
    # 老系统便携版默认不带 Tcl/Tk：不崩溃，自动降级到网页界面（同样是图形界面）。
    # pythonw.exe 没有控制台，这里用日志 + 自启 Web UI + 打开浏览器兜底。
    import subprocess
    import time
    import webbrowser
    import urllib.request
    _uh = os.path.join(os.path.expanduser("~"), ".miniagent")
    try:
        os.makedirs(_uh, exist_ok=True)
    except Exception:
        pass
    _log = os.path.join(_uh, "desktop.log")
    try:
        _port = 8787
        subprocess.Popen(
            [sys.executable, "run.py", "--web"],
            cwd=_PROJECT_DIR,
            stdout=open(os.path.join(_uh, "webui.stdout.log"), "w"),
            stderr=subprocess.STDOUT,
            creationflags=0x08000000,  # CREATE_NO_WINDOW（仅 Windows）
        )
        for _ in range(30):
            time.sleep(0.5)
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/" % _port, timeout=1)
                break
            except Exception:
                pass
        webbrowser.open("http://127.0.0.1:%d/" % _port)
        try:
            with open(_log, "a", encoding="utf-8") as _fh:
                _fh.write("[降级] 当前 Python 没有 tkinter（Tcl/Tk），已自动改用网页界面："
                          "http://127.0.0.1:%d/\n" % _port)
        except Exception:
            pass
    except Exception as _e:
        try:
            with open(_log, "a", encoding="utf-8") as _fh:
                _fh.write("[降级失败] %r\n" % _e)
        except Exception:
            pass
    sys.exit(0)

from miniagent.config import Config
from miniagent.onboarding import (EXAMPLES, PRESETS, apply_setup, check_setup,
                                 friendly_tool, humanize_error, setup_tips,
                                 test_connection)
from miniagent.runtime import Runtime
from miniagent import db

# ── 外观：DSH 风格（深色侧栏 + 浅色聊天区 + 圆润气泡），无 emoji ──
# 参考 DSH 桌面端配色：侧栏 #1E1F26 / 主区 #F7F7F9 / 强调蓝 #4A7CF5
# 纯 tkinter 实现，不用圆角/图片，靠配色与留白做出「现代聊天软件」的观感。
APP_TITLE = "MiniAgent"
WIN_W = 1080
WIN_H = 720
SIDE_W = 232
SIDE_BG = "#202127"       # 左侧会话栏（深）
SIDE_CARD = "#2B2D36"     # 侧栏卡片/选中项
SIDE_INK = "#EDEEF3"
SIDE_DIM = "#9397A6"
BG = "#F7F7F9"            # 主聊天区（浅）
CARD = "#FFFFFF"
INK = "#22242B"
MUTED = "#8A8F9C"
BLUE = "#4A7CF5"
BLUE_BG = "#E9EFFE"
ME_BUBBLE = "#4A7CF5"     # 我发消息：蓝底白字气泡
ME_INK = "#FFFFFF"
AGENT_BUBBLE = "#FFFFFF"  # 助手：白底卡片 + 细边
RED = "#D64541"
RED_BG = "#FDECEA"
LINE = "#E6E8EE"
FONT = ("Microsoft YaHei", 10)
FONT_BOLD = ("Microsoft YaHei", 10, "bold")
FONT_TITLE = ("Microsoft YaHei", 14, "bold")
FONT_SMALL = ("Microsoft YaHei", 9)
FONT_LOGO = ("Microsoft YaHei", 16, "bold")
CONFIRM_TIMEOUT = 90
POLL_MS = 80
LOG_NAME = "desktop.log"


# ── 日志与启动引导 ────────────────────────────────────────────
def _home_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".miniagent")


def _log_path() -> str:
    return os.path.join(_home_dir(), LOG_NAME)


def write_log(text: str) -> None:
    """pythonw.exe 下唯一可靠的输出口；任何情况下都不能因为日志失败而崩。"""
    try:
        d = _home_dir()
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(_log_path(), "a", encoding="utf-8") as fh:
            fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except Exception:
        pass


def _fatal(title: str, detail: str) -> None:
    write_log("%s: %s" % (title, detail))
    try:
        messagebox.showerror(APP_TITLE, "%s\n\n%s\n\n日志：%s"
                             % (title, detail, _log_path()))
    except Exception:
        pass


def _bootstrap() -> str:
    """把工作目录、标准输出、全局异常钩子准备好。返回程序所在目录。"""
    frozen = bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")
    if frozen:
        # sys.executable 是用户双击的 MiniAgent.exe；_MEIPASS 只是临时解压目录，
        # 数据文件（config/skills/plugins）要按 exe 所在的安装目录来找。
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_dir = _PROJECT_DIR
    try:
        os.chdir(base_dir)
    except OSError as exc:
        write_log("无法切换工作目录：%s" % exc)
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    try:
        d = _home_dir()
        if not os.path.isdir(d):
            os.makedirs(d)
        fh = open(_log_path(), "a", encoding="utf-8", buffering=1)
        sys.stdout = fh
        sys.stderr = fh
    except Exception as exc:
        write_log("无法重定向 stdout/stderr：%s" % exc)

    def _hook(etype: Any, value: Any, tb: Any) -> None:
        write_log("未捕获异常：\n" + "".join(traceback.format_exception(etype, value, tb)))
        try:
            messagebox.showerror(APP_TITLE, "程序出错：%s\n\n详情见 %s"
                                 % (value, _log_path()))
        except Exception:
            pass

    sys.excepthook = _hook
    write_log("启动 desktop.py | frozen=%s | base=%s | python=%s"
              % (frozen, base_dir, sys.version.split()[0]))
    return base_dir


def _make_runtime(base_dir: str, frozen: bool, home: Optional[str] = None) -> Runtime:
    """装配运行时；冻结时把扩展目录指向安装目录（而不是临时解压目录）。"""
    cfg = Config.load()
    if frozen:
        for key, folder in (("skills_dir", "skills"), ("plugins_dir", "plugins")):
            target = os.path.join(base_dir, folder)
            if os.path.isdir(target):
                cfg.set(key, target)
    rt = Runtime(cfg, home=home, session=None)
    rt.build()
    return rt


class _ProbeConfig(object):
    """临时配置：允许用向导里「还没保存」的值试连，不改动真实配置。"""

    def __init__(self, base: Config, overrides: Dict[str, Any]):
        self.base = base
        self.overrides = dict(overrides or {})

    def get(self, key: str, default: Any = None) -> Any:
        k = str(key)
        if k in self.overrides:
            return self.overrides[k]
        return self.base.get(k, default)


def _preset(preset_id: str) -> Dict[str, Any]:
    for item in PRESETS:
        if item["id"] == preset_id:
            return item
    return PRESETS[0]


def _preset_ids() -> List[str]:
    return [str(p["id"]) for p in PRESETS]


def _brief(text: Any, limit: int = 150) -> str:
    """折叠空白并截断，避免把一大段原始工具输出糊到界面上。"""
    s = " ".join(str(text or "").split())
    if len(s) > limit:
        return s[:limit] + " ..."
    return s


def _provider_label(provider: str) -> str:
    return {"mock": "演示模式", "ollama": "本地模型",
            "openai_compat": "云端模型"}.get(provider, provider or "未设置")


# ── 危险操作确认框（主线程）───────────────────────────────────
class ConfirmDialog(tk.Toplevel):
    """允许 / 拒绝；超时自动拒绝。默认按钮是「拒绝」。"""

    def __init__(self, parent: Any, rec: Dict[str, Any], text: str,
                 on_done: Any, timeout: int = CONFIRM_TIMEOUT):
        tk.Toplevel.__init__(self, parent)
        self.rec = rec
        self.on_done = on_done
        self.deadline = time.time() + timeout
        self.after_id: Any = None
        self.done = False

        self.title("需要你确认")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(bg=CARD)
        box = tk.Frame(self, bg=CARD, padx=18, pady=16)
        box.pack(fill="both", expand=True)

        tk.Label(box, text="这一步要你点头才做", font=FONT_BOLD, bg=CARD,
                 fg=INK, anchor="w").pack(fill="x")
        tk.Label(box, text=text, font=FONT, bg=CARD, fg=INK, anchor="w",
                 justify="left", wraplength=420).pack(fill="x", pady=(10, 4))
        tk.Label(box, text="写文件、执行命令、运行代码可能会改动你的电脑。不确定就选拒绝。",
                 font=FONT_SMALL, bg=CARD, fg=MUTED, anchor="w",
                 justify="left", wraplength=420).pack(fill="x")

        self.count_var = tk.StringVar()
        tk.Label(box, textvariable=self.count_var, font=FONT_SMALL, bg=CARD,
                 fg=RED, anchor="w").pack(fill="x", pady=(10, 0))

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(14, 0))
        tk.Button(row, text="拒绝", width=10, font=FONT, bg=CARD, fg=INK,
                  relief="solid", bd=1, command=lambda: self._finish(False)).pack(side="right", padx=(8, 0))
        tk.Button(row, text="允许", width=10, font=FONT, bg=BLUE_BG, fg=BLUE,
                  relief="solid", bd=1, command=lambda: self._finish(True)).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(False))
        try:
            self.grab_set()
        except Exception:
            pass
        self._tick()

    def _tick(self) -> None:
        if self.done:
            return
        left = int(self.deadline - time.time() + 0.999)
        if left <= 0:
            self._finish(False)
            return
        self.count_var.set("%d 秒后自动拒绝" % left)
        self.after_id = self.after(1000, self._tick)

    def _finish(self, allow: bool) -> None:
        if self.done:
            return
        self.done = True
        self.rec["allow"] = bool(allow)
        self.rec["event"].set()
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self.on_done:
            try:
                self.on_done(self.rec)
            except Exception:
                pass


# ── 设置向导（首次打开 / 右上角「设置」）───────────────────────
class SetupWizard(tk.Toplevel):
    """三选一 + 模型名 + API Key（掩码）+ 测试连接 + 保存并开始。"""

    def __init__(self, parent: Any, app: "DesktopApp", first_run: bool = False):
        tk.Toplevel.__init__(self, parent)
        self.app = app
        self.first_run = first_run
        self.test_result: Optional[Dict[str, Any]] = None
        cfg = app.rt.cfg
        state = check_setup(cfg)

        ids = _preset_ids()
        saved = str(cfg.get("onboarding.preset", "") or "")
        if saved not in ids:
            saved = {"mock": "demo", "ollama": "local",
                     "openai_compat": "cloud"}.get(str(cfg.get("provider", "") or ""), "demo")
        self.preset_var = tk.StringVar(value=saved)
        self.model_var = tk.StringVar(value=str(cfg.get("model", "") or ""))
        self.base_var = tk.StringVar(value=str(cfg.get("api_base", "") or ""))
        self.key_var = tk.StringVar(value="")
        self.tips_var = tk.StringVar()
        self.note_var = tk.StringVar()

        self.title("设置 · MiniAgent")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(bg=BG)
        self.geometry("560x590")

        outer = tk.Frame(self, bg=BG, padx=18, pady=14)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="选一个模型来源", font=FONT_TITLE, bg=BG, fg=INK,
                 anchor="w").pack(fill="x")
        tk.Label(outer, text="不用懂命令行，点一下就行。以后随时可以在右上角「设置」里改。",
                 font=FONT_SMALL, bg=BG, fg=MUTED, anchor="w",
                 justify="left").pack(fill="x", pady=(2, 12))

        for item in PRESETS:
            row = tk.Frame(outer, bg=CARD, padx=12, pady=8, relief="solid", bd=1)
            row.pack(fill="x", pady=4)
            tk.Radiobutton(row, text=item["title"], variable=self.preset_var,
                           value=item["id"], command=self._on_preset_change,
                           font=FONT_BOLD, bg=CARD, fg=INK, anchor="w",
                           selectcolor=CARD, activebackground=CARD).pack(fill="x")
            tk.Label(row, text=item["subtitle"], font=FONT_SMALL, bg=CARD,
                     fg=MUTED, anchor="w").pack(fill="x", padx=(20, 0))

        tk.Label(outer, textvariable=self.note_var, font=FONT_SMALL, bg=BG,
                 fg=MUTED, anchor="w", justify="left", wraplength=510).pack(fill="x", pady=(6, 4))

        detail = tk.LabelFrame(outer, text="详细设置", bg=BG, fg=INK, font=FONT,
                               padx=10, pady=8)
        detail.pack(fill="x", pady=(4, 6))
        detail.columnconfigure(1, weight=1)

        tk.Label(detail, text="模型名", font=FONT, bg=BG, fg=INK, anchor="w").grid(
            row=0, column=0, sticky="w", pady=3)
        tk.Entry(detail, textvariable=self.model_var, font=FONT, relief="solid",
                 bd=1).grid(row=0, column=1, sticky="ew", pady=3)

        tk.Label(detail, text="服务地址", font=FONT, bg=BG, fg=INK, anchor="w").grid(
            row=1, column=0, sticky="w", pady=3)
        tk.Entry(detail, textvariable=self.base_var, font=FONT, relief="solid",
                 bd=1).grid(row=1, column=1, sticky="ew", pady=3)

        tk.Label(detail, text="API Key", font=FONT, bg=BG, fg=INK, anchor="w").grid(
            row=2, column=0, sticky="w", pady=3)
        self.key_entry = tk.Entry(detail, textvariable=self.key_var, font=FONT,
                                  show="*", relief="solid", bd=1)
        self.key_entry.grid(row=2, column=1, sticky="ew", pady=3)
        self.key_hint = tk.StringVar()
        if state.get("api_key_set"):
            self.key_hint.set("已经保存过 Key，留空就表示不修改，界面不会显示完整内容。")
        else:
            self.key_hint.set("Key 只保存在你自己的用户目录里，不会写进项目文件夹。")
        tk.Label(detail, textvariable=self.key_hint, font=FONT_SMALL, bg=BG,
                 fg=MUTED, anchor="w", justify="left", wraplength=380).grid(
            row=3, column=0, columnspan=2, sticky="w")

        tk.Label(outer, textvariable=self.tips_var, font=FONT_SMALL, bg=BG,
                 fg=BLUE, anchor="w", justify="left", wraplength=510).pack(fill="x", pady=(2, 8))

        buttons = tk.Frame(outer, bg=BG)
        buttons.pack(fill="x", side="bottom")
        self.test_btn = tk.Button(buttons, text="测试连接", width=11, font=FONT,
                                  bg=CARD, fg=INK, relief="solid", bd=1,
                                  command=self._on_test)
        self.test_btn.pack(side="left")
        tk.Button(buttons, text="跳过，先用演示模式", font=FONT_SMALL, bg=BG,
                  fg=MUTED, relief="flat", command=self._on_skip).pack(side="left", padx=(8, 0))
        tk.Button(buttons, text="保存并开始", width=12, font=FONT_BOLD, bg=BLUE_BG,
                  fg=BLUE, relief="solid", bd=1,
                  command=self._on_save).pack(side="right")

        # 首次打开时保留用户已有配置；从没设置过就直接填预设推荐值
        never = not bool(cfg.get("onboarding.done", False))
        self._apply_preset_fields(reset=bool(first_run or never))
        self.protocol("WM_DELETE_WINDOW", self._on_skip if first_run else self._close)
        try:
            self.grab_set()
        except Exception:
            pass
        self.lift()
        self.focus_force()

    # ── 表单 ──
    def _apply_preset_fields(self, reset: bool) -> None:
        item = _preset(self.preset_var.get())
        conf = item["config"]
        if reset:
            self.model_var.set(str(conf.get("model", "") or ""))
            self.base_var.set(str(conf.get("api_base", "") or ""))
            self.key_var.set("")
        need = bool(item["need_key"])
        self.key_entry.configure(state="normal" if need else "disabled")
        self.tips_var.set(setup_tips(str(conf.get("provider", "") or "")))
        self.note_var.set(str(item.get("note", "") or ""))

    def _on_preset_change(self) -> None:
        self._apply_preset_fields(reset=True)

    def _payload(self) -> Dict[str, str]:
        return {
            "preset": self.preset_var.get(),
            "model": self.model_var.get().strip(),
            "api_base": self.base_var.get().strip(),
            "api_key": self.key_var.get().strip(),
        }

    def _probe_payload(self) -> Dict[str, str]:
        data = self._payload()
        item = _preset(self.preset_var.get())
        data["provider"] = str(item["config"].get("provider", "") or "")
        return data

    # ── 按钮 ──
    def _on_test(self) -> None:
        probe = _ProbeConfig(self.app.rt.cfg, self._probe_payload())
        self.test_result = None
        self.test_btn.configure(state="disabled", text="测试中…")

        def work() -> None:
            try:
                self.test_result = test_connection(probe, timeout=5)
            except Exception as exc:
                self.test_result = {"ok": False, "message": str(exc)}

        threading.Thread(target=work, daemon=True).start()
        self.after(120, self._poll_test)

    def _poll_test(self) -> None:
        if not self.winfo_exists():
            return
        if self.test_result is None:
            self.after(120, self._poll_test)
            return
        result = self.test_result
        self.test_btn.configure(state="normal", text="测试连接")
        title = "连上了" if result.get("ok") else "没连上"
        messagebox.showinfo(title, str(result.get("message", "") or ""), parent=self)

    def _on_save(self) -> None:
        result = apply_setup(self.app.rt.cfg, self._payload())
        if not result.get("ok"):
            messagebox.showerror("设置没保存", str(result.get("message", "") or ""),
                                 parent=self)
            return
        self.app.after_setup(result)
        self._close()

    def _on_skip(self) -> None:
        result = apply_setup(self.app.rt.cfg, {"preset": "demo"})
        if result.get("ok"):
            self.app.after_setup(result)
        else:
            write_log("跳过向导进入演示模式失败：%s" % result.get("message", ""))
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        self.app.on_wizard_closed()


# ── 主窗口 ──────────────────────────────────────────────────
class DesktopApp(object):
    def __init__(self, root: Any, rt: Runtime, base_dir: str, frozen: bool):
        self.root = root
        self.rt = rt
        self.base_dir = base_dir
        self.frozen = frozen
        self.events: "queue.Queue" = queue.Queue()
        self.pending_confirms: List[Dict[str, Any]] = []
        self.confirm_dialog: Any = None
        self.wizard: Any = None
        self.busy = False
        self.closing = False
        self.answer_started = False
        self.answer_len = 0
        self.error_shown = False
        self.current_step = 0
        self.step_max = 0
        self.status_var = tk.StringVar()

        root.title(APP_TITLE)
        root.geometry("%dx%d" % (WIN_W, WIN_H))
        root.minsize(880, 600)
        root.configure(bg=BG)
        self._session_items: List[Any] = []
        # ── 多会话：启动时确保至少一个会话，记住当前会话 ID ──
        db.init_db()
        _sessions = db.list_sessions()
        self.current_sid: Optional[str] = (
            _sessions[0]["id"] if _sessions else db.create_session("新的对话"))
        self._build_ui()
        self._load_session(self.current_sid, silent=True)
        self._wire_agent()
        self._set_status("")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(POLL_MS, self._poll)

    # ── 布局（DSH 风格：左会话栏 + 右主区；全 grid，避免 pack 挤压 1x1）──
    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=0, minsize=SIDE_W)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # ===== 左侧会话栏（深色）=====
        side = tk.Frame(root, bg=SIDE_BG, width=SIDE_W)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(3, weight=1)

        logo = tk.Frame(side, bg=SIDE_BG)
        logo.grid(row=0, column=0, sticky="ew", padx=16, pady=(18, 14))
        tk.Label(logo, text="MiniAgent", font=FONT_LOGO, bg=SIDE_BG,
                 fg=SIDE_INK, anchor="w").pack(anchor="w")
        tk.Label(logo, text="本地 AI 助手 · Win7 可用", font=FONT_SMALL,
                 bg=SIDE_BG, fg=SIDE_DIM, anchor="w").pack(anchor="w", pady=(3, 0))

        tk.Button(side, text="+  新建对话", font=FONT_BOLD, bg="#3A5FD9",
                  fg="#FFFFFF", activebackground="#4A7CF5", activeforeground="#FFFFFF",
                  relief="flat", bd=0, cursor="hand2", padx=10, pady=7,
                  anchor="w", command=self.new_chat).grid(
                      row=1, column=0, sticky="ew", padx=12, pady=(0, 14))

        tk.Label(side, text="最近会话", font=FONT_SMALL, bg=SIDE_BG,
                 fg=SIDE_DIM, anchor="w").grid(
                     row=2, column=0, sticky="ew", padx=18, pady=(0, 6))

        sess = tk.Frame(side, bg=SIDE_BG)
        sess.grid(row=3, column=0, sticky="nsew", padx=8)
        sess.columnconfigure(0, weight=1)
        # 用 Canvas + 内部 Frame 实现可滚动会话列表（Tk 的 Listbox 无法做多色圆角）
        self._sess_canvas = tk.Canvas(sess, bg=SIDE_BG, highlightthickness=0)
        self._sess_canvas.grid(row=0, column=0, sticky="nsew")
        self._sess_inner = tk.Frame(self._sess_canvas, bg=SIDE_BG)
        self._sess_win = self._sess_canvas.create_window(
            (0, 0), window=self._sess_inner, anchor="nw")
        self._sess_canvas.bind("<Configure>", self._on_sess_resize)
        self._sess_canvas.bind("<MouseWheel>", self._on_sess_wheel)
        self._sess_canvas.bind("<Button-4>", self._on_sess_wheel)
        self._sess_canvas.bind("<Button-5>", self._on_sess_wheel)
        self._refresh_sessions()

        foot = tk.Frame(side, bg=SIDE_BG)
        foot.grid(row=4, column=0, sticky="sew", padx=12, pady=12)
        tk.Button(foot, text="设置", font=FONT_SMALL, bg=SIDE_CARD, fg=SIDE_INK,
                  activebackground="#3A3D48", activeforeground=SIDE_INK,
                  relief="flat", bd=0, cursor="hand2", padx=12, pady=5,
                  command=self.open_settings).pack(side="left")
        tk.Label(foot, textvariable=self.status_var, font=FONT_SMALL, bg=SIDE_BG,
                 fg=SIDE_DIM, anchor="w").pack(side="right", fill="x", expand=True)

        # ===== 右侧主区 =====
        main = tk.Frame(root, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(2, weight=0)

        # 顶栏
        top = tk.Frame(main, bg=CARD, padx=18, pady=11)
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(top, text="对话", font=FONT_BOLD, bg=CARD, fg=INK,
                 anchor="w").pack(side="left")
        self.mode_var = tk.StringVar()
        self.mode_box = ttk.Combobox(top, textvariable=self.mode_var, state="readonly",
                                     width=9, font=FONT_SMALL)
        self.mode_box.pack(side="right", padx=(8, 0))
        self.mode_box.bind("<<ComboboxSelected>>", self._on_mode_pick)
        self.model_var = tk.StringVar()
        self.model_box = ttk.Combobox(top, textvariable=self.model_var, state="readonly",
                                      width=26, font=FONT_SMALL)
        self.model_box.pack(side="right", padx=(8, 0))
        self.model_box.bind("<<ComboboxSelected>>", self._on_model_pick)
        self._refresh_pickers()

        # 底部输入区（先建先放；消息区拿 weight，输入区固定高度，不会被压 1x1）
        bottom = tk.Frame(main, bg=BG, padx=18, pady=12)
        bottom.grid(row=2, column=0, sticky="ew")
        inp_wrap = tk.Frame(bottom, bg=CARD, highlightbackground=LINE,
                            highlightthickness=1)
        inp_wrap.pack(side="top", fill="x")
        self.input = tk.Text(inp_wrap, height=3, wrap="word", font=FONT,
                             relief="flat", bd=0, bg=CARD, fg=INK, padx=10, pady=8)
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", self._on_return)
        tk.Button(inp_wrap, text="发送", width=8, font=FONT_BOLD, bg=BLUE,
                  fg="#FFFFFF", activebackground="#3A6AE0", activeforeground="#FFFFFF",
                  relief="flat", bd=0, cursor="hand2", command=self.send).pack(
                      side="right", padx=(6, 8), pady=8, fill="y")
        hint_row = tk.Frame(bottom, bg=BG)
        hint_row.pack(side="top", fill="x", pady=(6, 0))
        tk.Label(hint_row, text="Enter 发送 · Shift+Enter 换行", font=FONT_SMALL,
                 bg=BG, fg=MUTED, anchor="w").pack(side="left")
        tk.Button(hint_row, text="清空", font=FONT_SMALL, bg=BG, fg=MUTED,
                  relief="flat", bd=0, cursor="hand2", command=self.clear_chat).pack(side="right")

        # 中间消息区：grid + weight=1 吃掉全部弹性空间
        middle = tk.Frame(main, bg=BG, padx=18, pady=10)
        middle.grid(row=1, column=0, sticky="nsew")
        middle.columnconfigure(0, weight=1)
        middle.rowconfigure(0, weight=1)
        self.text = tk.Text(middle, height=10, wrap="word", state="disabled", bg=BG,
                            fg=INK, font=FONT, relief="flat", bd=0,
                            padx=4, pady=4, spacing1=3, spacing3=3)
        scroll = ttk.Scrollbar(middle, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.grid(row=0, column=0, sticky="nsew")
        self._configure_tags()
        self._build_welcome()

        # withdraw 期间 focus_set 无效；等窗口真正 map 后再把光标放进输入框。
        self.root.bind("<Map>", self._on_map_focus, add="+")
        self.root.after(120, self._focus_input)

    def _on_map_focus(self, event: Any) -> None:
        self._focus_input()

    def _focus_input(self) -> None:
        if self.closing:
            return
        try:
            self.input.focus_force()
        except Exception:
            try:
                self.input.focus_set()
            except Exception:
                pass

    def _configure_tags(self) -> None:
        """气泡样式：我用大左边距+蓝底靠右，助手用小左边距+白卡靠左。"""
        t = self.text
        t.tag_config("me_label", foreground=BLUE, background=BG,
                     font=FONT_SMALL, lmargin1=300, lmargin2=300, rmargin=20,
                     spacing1=8, spacing3=0)
        t.tag_config("me", foreground=ME_INK, background=ME_BUBBLE,
                     font=FONT, lmargin1=300, lmargin2=300, rmargin=20,
                     spacing1=0, spacing3=2)
        t.tag_config("agent_label", foreground=MUTED, background=BG,
                     font=FONT_SMALL, lmargin1=16, lmargin2=16, rmargin=120,
                     spacing1=8, spacing3=0)
        t.tag_config("agent", foreground=INK, background=AGENT_BUBBLE,
                     font=FONT, lmargin1=16, lmargin2=16, rmargin=120,
                     spacing1=0, spacing3=2)
        t.tag_config("hint", foreground=MUTED, background=BG,
                     font=FONT_SMALL, lmargin1=18, lmargin2=18, rmargin=18,
                     spacing1=1, spacing3=1)
        t.tag_config("error_title", foreground=RED, background=RED_BG,
                     font=FONT_BOLD, lmargin1=16, lmargin2=16, rmargin=60,
                     spacing1=6, spacing3=2)
        t.tag_config("error_body", foreground=RED, background=RED_BG,
                     font=FONT, lmargin1=16, lmargin2=16, rmargin=60, spacing3=8)

    # ── 多会话管理 ──
    def _on_sess_resize(self, event: Any) -> None:
        try:
            self._sess_canvas.itemconfigure(self._sess_win, width=event.width)
        except Exception:
            pass

    def _on_sess_wheel(self, event: Any) -> str:
        try:
            step = -1 if (event.num == 4 or event.delta > 0) else 1
            self._sess_canvas.yview_scroll(step, "units")
        except Exception:
            pass
        return "break"

    def _refresh_sessions(self) -> None:
        """按数据库内容重建左侧会话列表。"""
        inner = getattr(self, "_sess_inner", None)
        if inner is None:
            return
        for w in list(inner.winfo_children()):
            w.destroy()
        self._session_items = []
        rows = db.list_sessions()
        if not rows:
            tk.Label(inner, text="  （还没有会话）", font=FONT_SMALL,
                     bg=SIDE_BG, fg=SIDE_DIM, anchor="w",
                     padx=8, pady=7).grid(row=0, column=0, sticky="ew")
            return
        for i, row in enumerate(rows):
            sid = row["id"]
            active = (sid == self.current_sid)
            base = SIDE_CARD if active else SIDE_BG
            item = tk.Frame(inner, bg=base)
            item.grid(row=i, column=0, sticky="ew")
            item.columnconfigure(0, weight=1)
            title = row["title"] or "新的对话"
            if len(title) > 12:
                title = title[:11] + "…"
            tk.Button(item, text="  " + title, font=FONT, bg=base,
                      fg=SIDE_INK if active else SIDE_DIM,
                      activebackground="#3A3D48", activeforeground=SIDE_INK,
                      relief="flat", bd=0, anchor="w", cursor="hand2",
                      command=lambda s=sid: self._load_session(s)).grid(
                          row=0, column=0, sticky="ew", pady=2)
            tk.Button(item, text="×", font=FONT_SMALL, bg=base,
                      fg=SIDE_DIM, activebackground="#3A3D48",
                      relief="flat", bd=0, cursor="hand2", width=2,
                      command=lambda s=sid: self._delete_session(s)).grid(
                          row=0, column=1, sticky="e", padx=(0, 6))
            self._session_items.append(item)
        try:
            self._sess_canvas.configure(scrollregion=self._sess_canvas.bbox("all"))
        except Exception:
            pass

    def _sync_memory(self, sid: str) -> None:
        """把 Agent 的短期记忆切到指定会话，避免跨会话串话。"""
        try:
            mem = self.rt.memory
            msgs = db.list_messages(sid)
            mem.name = sid
            mem.path = os.path.join(mem.session_dir, sid + ".jsonl")
            mem._messages = [{"role": m["role"], "content": m["content"]}
                             for m in msgs]
        except Exception as exc:
            write_log("切换会话记忆失败：%s" % exc)

    def _load_session(self, sid: Optional[str], silent: bool = False) -> None:
        if not sid:
            return
        if self.busy and not silent:
            messagebox.showinfo(APP_TITLE, "正在回复中，等这一句说完再切换。",
                                parent=self.root)
            return
        self.current_sid = sid
        self._sync_memory(sid)
        msgs = db.list_messages(sid)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        if msgs:
            for m in msgs:
                if m["role"] == "user":
                    self._append_user(m["content"])
                elif m["role"] == "assistant":
                    self._insert("MiniAgent\n", "agent_label")
                    self._insert(m["content"] + "\n", "agent")
        else:
            self._build_welcome()
        self._refresh_sessions()
        if not silent:
            self._set_status("")
            self._focus_input()

    def new_chat(self) -> None:
        if self.busy:
            messagebox.showinfo(APP_TITLE, "正在回复中，等这一句说完再新建。",
                                parent=self.root)
            return
        sid = db.create_session("新的对话")
        if not sid:
            messagebox.showerror(APP_TITLE, "创建会话失败，请看桌面日志。",
                                 parent=self.root)
            return
        self._load_session(sid)

    def _delete_session(self, sid: str) -> None:
        if self.busy:
            messagebox.showinfo(APP_TITLE, "正在回复中，等这一句说完再删除。",
                                parent=self.root)
            return
        if not messagebox.askyesno(APP_TITLE, "确定删除这个会话？不可恢复。",
                                   parent=self.root):
            return
        db.delete_session(sid)
        rows = db.list_sessions()
        if sid == self.current_sid:
            if rows:
                self._load_session(rows[0]["id"])
            else:
                self._load_session(db.create_session("新的对话"))
        else:
            self._refresh_sessions()

    def _build_welcome(self) -> None:
        """6 个可点击示例卡片，直接嵌在消息区顶部。"""
        frame = tk.Frame(self.text, bg=CARD, padx=4, pady=4)
        tk.Label(frame, text="不知道说什么？点一个试试", font=FONT_BOLD, bg=CARD,
                 fg=INK, anchor="w").pack(fill="x", pady=(0, 2))
        tk.Label(frame, text="下面都是只看看、不改文件的任务，放心点。", font=FONT_SMALL,
                 bg=CARD, fg=MUTED, anchor="w").pack(fill="x", pady=(0, 8))
        grid = tk.Frame(frame, bg=CARD)
        grid.pack(fill="x")
        for i, ex in enumerate(EXAMPLES):
            label = "[%s] %s\n%s" % (ex["tag"], ex["title"], ex["prompt"])
            btn = tk.Button(grid, text=label, font=FONT_SMALL, bg=CARD, fg=INK,
                            activebackground=BLUE_BG, relief="flat", bd=0,
                            highlightbackground=LINE, highlightthickness=1,
                            anchor="w", justify="left", wraplength=250,
                            padx=10, pady=8, cursor="hand2",
                            command=lambda p=ex["prompt"]: self.send(p))
            btn.grid(row=i // 3, column=i % 3, sticky="nsew", padx=4, pady=4)
        for col in range(3):
            grid.columnconfigure(col, weight=1)

        self.text.configure(state="normal")
        self.text.insert("end", "", "hint")
        self.text.window_create("end", window=frame)
        self.text.insert("end", "\n\n", "hint")
        self.text.configure(state="disabled")
        self.text.see("end")

    # ── 文本插入（Text 平时是 disabled，避免用户改到历史记录）──
    def _insert(self, content: str, tag: str = "agent") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", content, tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    def _embed(self, widget: Any) -> None:
        self.text.configure(state="normal")
        self.text.window_create("end", window=widget)
        self.text.insert("end", "\n", "hint")
        self.text.configure(state="disabled")
        self.text.see("end")

    def _append_user(self, content: str) -> None:
        self._insert("我\n", "me_label")
        self._insert(content + "\n", "me")

    def _append_hint(self, content: str) -> None:
        self._insert(content + "\n", "hint")

    def _close_answer(self) -> None:
        if self.answer_started:
            self._insert("\n", "agent")
        self.answer_started = False
        self.answer_len = 0

    # ── 事件渲染 ──
    def _render(self, kind: str, data: Any) -> None:
        if kind == "delta":
            chunk = str(data or "")
            if not self.answer_started:
                self._insert("MiniAgent\n", "agent_label")
                self.answer_started = True
            self._insert(chunk, "agent")
            self.answer_len += len(chunk)
            self.answer_buf.append(chunk)
        elif kind == "step":
            info = data if isinstance(data, dict) else {}
            self.current_step = int(info.get("step", 1) or 1)
            self.step_max = int(info.get("max", 1) or 1)
            self._append_hint("· 第 %d 步（最多 %d 步）" % (self.current_step, self.step_max))
        elif kind == "tool_call":
            info = data if isinstance(data, dict) else {}
            self._close_answer()
            name = str(info.get("name", "") or "")
            line = "第 %d 步 · %s" % (self.current_step or 1,
                                    friendly_tool(name, info.get("arguments")))
            if info.get("risky"):
                line += "（需要你确认）"
            self._append_hint(line)
        elif kind == "tool_result":
            info = data if isinstance(data, dict) else {}
            out = _brief(info.get("output", ""), 150)
            self._append_hint("   → " + (out or "做完了"))
        elif kind == "error":
            self._close_answer()
            provider = str(self.rt.cfg.get("provider", "") or "")
            info = humanize_error(data, provider)
            self._insert("出了问题 · %s\n" % info["title"], "error_title")
            self._insert("%s\n下一步：%s\n"
                         % (info["detail"], _next_action(info.get("action", ""))),
                         "error_body")
            btn = tk.Button(self.text, text="去设置", font=FONT_SMALL, bg=CARD,
                            fg=BLUE, relief="solid", bd=1,
                            command=self.open_settings)
            self._embed(btn)
            self.error_shown = True
            write_log("对话报错：%s | 原始：%s" % (info["title"], info["raw"]))
        elif kind == "final":
            self._finish_answer(str(data or ""))
        elif kind == "worker_done":
            self._finish_answer("")

    def _finish_answer(self, final: str) -> None:
        if not self.busy:
            return
        if self.answer_started:
            if self.answer_len == 0 and final and not self.error_shown:
                self._insert(final, "agent")
            self._close_answer()
        elif final and not self.error_shown:
            self._insert("MiniAgent\n", "agent_label")
            self._insert(final + "\n", "agent")
        if self.current_sid and not self.error_shown:
            answer = (final or "").strip() or "".join(self.answer_buf).strip()
            if answer:
                db.add_message(self.current_sid, "assistant", answer)
                self._refresh_sessions()
        self.answer_buf = []
        self.busy = False
        self._set_status("")

    def _set_status(self, extra: str) -> None:
        cfg = self.rt.cfg
        provider = str(cfg.get("provider", "") or "")
        model = str(cfg.get("model", "") or "未设置")
        text = "当前：%s · %s" % (_provider_label(provider), model)
        if extra:
            text += " · " + extra
        self.status_var.set(text)

    # ── 模型目录 / 模式下拉 ──────────────────────────────────
    def _refresh_pickers(self) -> None:
        try:
            cat = self.rt.model_catalog()
            labels = ["%s%s · %s" % ("★ " if m["active"] else "", m["label"], m["model"])
                      for m in cat["models"]]
            self.model_box["values"] = labels
            self._model_ids = [m["id"] for m in cat["models"]]
            cur = cat["active_model"]
            self.model_var.set(labels[self._model_ids.index(cur)]
                               if cur in self._model_ids and labels else "")
            mcat = self.rt.mode_catalog()
            ml = ["%s模式" % m["label"] for m in mcat["modes"]]
            self.mode_box["values"] = ml
            self._mode_ids = [m["id"] for m in mcat["modes"]]
            active = mcat["active"]
            self.mode_var.set(ml[self._mode_ids.index(active)]
                              if active in self._mode_ids and ml else "")
        except Exception as exc:
            write_log("刷新模型下拉失败：%s" % exc)

    def _on_model_pick(self, event: Any = None) -> None:
        try:
            idx = list(self.model_box["values"]).index(self.model_var.get())
            mid = self._model_ids[idx]
        except (ValueError, IndexError, AttributeError):
            return
        result = self.rt.use_model(mid)
        if result.get("ok"):
            self._wire_agent()
            self._set_status("")
            self._append_hint(result["message"])
        else:
            messagebox.showwarning("切换失败", str(result.get("message", "")), parent=self.root)
        self._refresh_pickers()

    def _on_mode_pick(self, event: Any = None) -> None:
        try:
            idx = list(self.mode_box["values"]).index(self.mode_var.get())
            mid = self._mode_ids[idx]
        except (ValueError, IndexError, AttributeError):
            return
        result = self.rt.set_mode(mid)
        if result.get("ok"):
            self._wire_agent()
            self._append_hint(result["message"])
        self._refresh_pickers()

    # ── 输入与后台对话 ──
    def _on_return(self, event: Any) -> str:
        self.send()
        return "break"

    def send(self, content: Optional[str] = None) -> None:
        if self.closing:
            return
        if content is None:
            content = self.input.get("1.0", "end").strip()
        content = str(content or "").strip()
        if not content:
            return
        if self.busy:
            messagebox.showinfo(APP_TITLE, "正在回复中，等这一句说完再发。",
                                parent=self.root)
            return
        self.input.delete("1.0", "end")
        self._append_user(content)
        if self.current_sid:
            db.add_message(self.current_sid, "user", content)
            user_count = len([m for m in db.list_messages(self.current_sid)
                              if m["role"] == "user"])
            if user_count == 1:
                db.rename_session(self.current_sid, content[:24])
                self._refresh_sessions()
        self.busy = True
        self.answer_buf = []
        self.answer_started = False
        self.answer_len = 0
        self.error_shown = False
        self.current_step = 0
        self.step_max = 0
        self._set_status("正在回复…")
        threading.Thread(target=self._chat_worker, args=(content,),
                         daemon=True).start()

    def _chat_worker(self, content: str) -> None:
        try:
            agent = self.rt.agent
            if agent is None:
                raise RuntimeError("运行时还没准备好")
            agent.chat(content, stream=bool(self.rt.cfg.get("stream", True)))
        except Exception as exc:
            write_log("对话线程异常：\n" + traceback.format_exc())
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("worker_done", None))

    def clear_chat(self) -> None:
        if self.busy:
            messagebox.showinfo(APP_TITLE, "正在回复中，等一下再清空。",
                                parent=self.root)
            return
        if self.current_sid:
            db.clear_messages(self.current_sid)
            self._sync_memory(self.current_sid)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._build_welcome()
        self._append_hint("当前会话已清空，可以重新开始。")
        self._refresh_sessions()

    # ── 主线程轮询 ──
    def _poll(self) -> None:
        if self.closing:
            return
        try:
            for _ in range(300):
                item = self.events.get_nowait()
                self._handle(item)
        except queue.Empty:
            pass
        except Exception:
            write_log("界面刷新异常：\n" + traceback.format_exc())
        if not self.closing:
            self.root.after(POLL_MS, self._poll)

    def _handle(self, item: Any) -> None:
        if not isinstance(item, tuple) or len(item) != 2:
            return
        kind, data = item
        if kind == "confirm":
            self._open_confirm(data if isinstance(data, dict) else {})
            return
        if self.closing:
            return
        try:
            self._render(str(kind), data)
        except Exception:
            write_log("渲染事件异常：\n" + traceback.format_exc())

    # ── 危险操作确认：worker 只等 Event，绝不默认放行 ──
    def _wire_agent(self) -> None:
        agent = self.rt.agent
        if agent is None:
            raise RuntimeError("运行时没有 Agent")
        agent.on_event = self._on_event_from_worker
        agent.confirm = self._confirm_from_worker
        # 桌面版一律逐条确认；即使配置里写过 auto_confirm=true 也不静默放行
        agent.auto_confirm = False

    def _on_event_from_worker(self, kind: str, data: Any) -> None:
        self.events.put((str(kind), data))

    def _confirm_from_worker(self, tool: Any, arguments: Any) -> bool:
        rec: Dict[str, Any] = {"event": threading.Event(), "allow": False}
        try:
            name = str(getattr(tool, "name", "") or "")
            text = friendly_tool(name, arguments) + "。\n确定要让 MiniAgent 做这一步吗？"
            self.events.put(("confirm", {"record": rec, "text": text, "name": name}))
            rec["event"].wait(CONFIRM_TIMEOUT)
            allowed = bool(rec.get("allow"))
            if not allowed:
                write_log("危险操作被拒绝或超时：%s" % name)
            return allowed
        except Exception:
            write_log("确认回调异常，按拒绝处理：\n" + traceback.format_exc())
            return False

    def _open_confirm(self, data: Dict[str, Any]) -> None:
        rec = data.get("record")
        if not isinstance(rec, dict):
            return
        self.pending_confirms.append(rec)
        if self._dialog_alive():
            # 同时只允许一个确认框；后来的直接拒绝，避免堆积
            rec["allow"] = False
            rec["event"].set()
            return
        try:
            self.confirm_dialog = ConfirmDialog(
                self.root, rec, str(data.get("text", "") or ""), self._confirm_done)
            self.confirm_dialog.lift()
            self.confirm_dialog.focus_force()
        except Exception:
            write_log("确认框创建失败，按拒绝处理：\n" + traceback.format_exc())
            rec["allow"] = False
            rec["event"].set()

    def _dialog_alive(self) -> bool:
        dlg = self.confirm_dialog
        if dlg is None:
            return False
        try:
            return bool(dlg.winfo_exists())
        except Exception:
            return False

    def _confirm_done(self, rec: Dict[str, Any]) -> None:
        self.confirm_dialog = None
        try:
            self.pending_confirms.remove(rec)
        except ValueError:
            pass

    # ── 设置 ──
    def open_settings(self, first_run: bool = False) -> None:
        if self._wizard_alive():
            try:
                self.wizard.lift()
            except Exception:
                pass
            return
        try:
            self.wizard = SetupWizard(self.root, self, first_run=first_run)
        except Exception:
            _fatal("设置窗口打不开", traceback.format_exc())

    def open_first_run_wizard(self) -> None:
        self.open_settings(first_run=True)

    def _wizard_alive(self) -> bool:
        w = self.wizard
        if w is None:
            return False
        try:
            return bool(w.winfo_exists())
        except Exception:
            return False

    def on_wizard_closed(self) -> None:
        self.wizard = None
        # 向导关掉后把光标还给输入框（首次启动也能「打开即可打字」）
        self.root.after(60, self._focus_input)

    def after_setup(self, result: Dict[str, Any]) -> None:
        """向导改的是顶层标量；同步回模型目录并重建后端（与 WebUI 一致）。"""
        try:
            mid = self.rt.models.active_id() or "default"
            cfg = self.rt.cfg
            saved = self.rt.save_model({
                "id": mid,
                "label": str(cfg.get("model", "") or mid),
                "provider": str(cfg.get("provider", "") or "openai_compat"),
                "model": str(cfg.get("model", "") or ""),
                "api_base": str(cfg.get("api_base", "") or ""),
                "api_key": str(cfg.get("api_key", "") or ""),
                "enabled": True,
            })
            if not saved.get("ok"):
                raise RuntimeError(str(saved.get("message", "模型目录同步失败")))
            self._wire_agent()
        except Exception as exc:
            write_log("重建模型后端失败：\n" + traceback.format_exc())
            _fatal("模型没切换成功", str(exc))
            return
        self._refresh_pickers()
        self._set_status("")
        self._append_hint(str(result.get("message", "") or "设置已保存"))

    # ── 关闭 ──
    def on_close(self) -> None:
        if self.busy:
            if not messagebox.askokcancel(APP_TITLE, "还在回复中，确定要退出吗？",
                                          parent=self.root):
                return
        self.closing = True
        for rec in list(self.pending_confirms):
            rec["allow"] = False
            rec["event"].set()
        try:
            self.rt.shutdown()
        except Exception as exc:
            write_log("关闭运行时出错：%s" % exc)
        write_log("窗口关闭")
        try:
            self.root.destroy()
        except Exception:
            pass


def _next_action(action: str) -> str:
    return {
        "setup": "点下面的「去设置」检查一下模型来源和 Key。",
        "retry": "再问一次试试；一直不行就去设置里换一个模型来源。",
        "network": "检查网络，或者确认本地模型服务已经打开。",
    }.get(action, "再试一次，不行就打开设置检查配置。")


def _run_selftest(base_dir: str, frozen: bool, report_path: str) -> int:
    """构建自检：验证冻结后 Tcl/Tk 与扩展目录可用，不创建任何窗口。

    由环境变量 MINIAGENT_SELFTEST=<报告文件路径> 触发，只给打包验证用。
    """
    lines: List[str] = ["frozen=%s" % frozen, "cwd=%s" % os.getcwd()]
    ok = False
    try:
        interpreter = tk.Tcl()  # 只建 Tcl 解释器，不弹窗口
        lines.append("tcl_version=%s" % interpreter.call("set", "tcl_version"))
        tmp_home = tempfile.mkdtemp(prefix="miniagent_selftest_")
        try:
            rt = _make_runtime(base_dir, frozen, home=tmp_home)
            lines.append("tools=%d" % len(rt.registry.names()))
            lines.append("skills=%d" % len(rt.skills.names()))
            lines.append("skills_dir=%s" % rt.cfg.get("skills_dir"))
            lines.append("plugins_dir=%s" % rt.cfg.get("plugins_dir"))
            lines.append("configured=%s" % bool(check_setup(rt.cfg)["configured"]))
            rt.shutdown()
        finally:
            shutil.rmtree(tmp_home, ignore_errors=True)
        ok = True
        lines.append("RESULT=OK")
    except Exception:
        lines.append("RESULT=FAIL")
        lines.append(traceback.format_exc())
    try:
        d = os.path.dirname(os.path.abspath(report_path))
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except Exception:
        write_log("自检报告写不出来：\n" + traceback.format_exc())
    write_log("自检：\n" + "\n".join(lines))
    return 0 if ok else 1


def main() -> int:
    base_dir = _bootstrap()
    frozen = bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")
    selftest = os.environ.get("MINIAGENT_SELFTEST", "").strip()
    if selftest:
        return _run_selftest(base_dir, frozen, selftest)
    try:
        root = tk.Tk()
        root.withdraw()
    except Exception as exc:
        _fatal("窗口创建失败", str(exc) + "\n" + traceback.format_exc())
        return 1
    try:
        rt = _make_runtime(base_dir, frozen)
        app = DesktopApp(root, rt, base_dir, frozen)
        root.deiconify()
        if not check_setup(rt.cfg).get("configured"):
            root.after(200, app.open_first_run_wizard)
        root.mainloop()
    except Exception as exc:
        _fatal("启动失败", str(exc) + "\n" + traceback.format_exc())
        try:
            root.destroy()
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
