# -*- coding: utf-8 -*-
"""插件化内核 + 模型目录 + 运行时模式的单测。

不联网、不写用户真实 ~/.miniagent：所有写操作用临时 home 隔离。
运行： python tests/test_kernel.py
"""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from miniagent.config import Config  # noqa: E402
from miniagent.kernel import (EVENT_REQUEST, Disposer, Kernel,  # noqa: E402
                              Plugin)
from miniagent.mode import mode_catalog, mode_ids, normalize_mode  # noqa: E402
from miniagent.models import ModelRegistry  # noqa: E402
from miniagent.runtime import Runtime  # noqa: E402

PASS = [0]
FAIL = [0]


def check(name, cond, detail=""):
    if cond:
        PASS[0] += 1
        print("PASS  %s" % name)
    else:
        FAIL[0] += 1
        print("FAIL  %s  %s" % (name, detail))


def cfg_with(data):
    return Config(data)


# ── 1. 服务定位 ──────────────────────────────────────────────
def test_services():
    k = Kernel()
    d = k.provide("foo", 42)
    check("服务注册/读取", k.get("foo") == 42)
    check("服务 require", k.require("foo") == 42)
    check("缺失服务给默认值", k.get("nope", "D") == "D")
    d()
    check("服务可撤销", k.get("foo") is None)
    try:
        k.require("foo")
        check("require 缺服务应抛错", False)
    except KeyError:
        check("require 缺服务应抛错", True)
    k.dispose()


# ── 2. 事件链：观察者 / 拦截器 / 改写 / 短路 ─────────────────
def test_events():
    k = Kernel()
    seen = []
    k.on("e", lambda p: seen.append(p))
    check("观察者收到载荷", k.emit("e", 7) == 7 and seen == [7])

    k.on("e", lambda p, nxt: nxt(p + 1), prepend=True)
    check("拦截器可改写载荷", k.emit("e", 7) == 8, k.emit("e", 7))
    check("改写后观察者看到新值", seen[-1] == 8, seen)

    k2 = Kernel()
    k2.on("e", lambda p, nxt: "STOP")
    k2.on("e", lambda p: seen.append("SHOULD_NOT_RUN"))
    k2.emit("e", 1)
    check("拦截器短路可阻断下游", "SHOULD_NOT_RUN" not in seen)

    k3 = Kernel()
    def broken(p, nxt):
        raise RuntimeError("boom")
    k3.on("e", broken)
    k3.on("e", lambda p, nxt: nxt(p + 10))
    check("单个监听者异常不炸整条链", k3.emit("e", 1) == 11, k3.emit("e", 1))

    k4 = Kernel()
    k4.on("e", lambda p, nxt: nxt(p * 2))
    check("拦截器显式返回值优先", k4.emit("e", 5) == 10)
    k.dispose()
    k2.dispose()
    k3.dispose()
    k4.dispose()


# ── 3. 副作用 / 依赖注入 / 槽位 / 分段提示词 ─────────────────
def test_scope_sections_slots():
    k = Kernel()
    cleaned = []
    k.effect(lambda ctx: (lambda: cleaned.append(1)))
    d = k.effect(lambda: None)
    check("effect 返回 Disposer", isinstance(d, Disposer))
    d()
    d()
    check("Disposer 幂等", True)

    try:
        k.inject(("missing",), lambda ctx: None)
        check("inject 缺依赖应抛错", False)
    except KeyError:
        check("inject 缺依赖应抛错", True)

    k.provide("a", 1)
    k.inject(("a",), lambda ctx: ctx.provide("b", 2))
    check("inject 依赖齐备可执行", k.get("b") == 2)

    k.slot("ui.top", "x", "X", order=10)
    k.slot("ui.top", "y", "Y", order=5)
    check("槽位按 order 排序", k.contributions("ui.top") == ["Y", "X"],
          k.contributions("ui.top"))
    check("槽位名可枚举", "ui.top" in k.slot_names())

    k.section("persona", "PERSONA", order=0)
    k.section("mode", "MODE", order=10)
    k.section("extra", "EXTRA", order=5)
    out = k.compose_prompt("BASE")
    check("分段提示词按 order 合成",
          out == "BASE\n\nPERSONA\n\nEXTRA\n\nMODE", repr(out))
    check("段名顺序", k.section_names() == ["persona", "extra", "mode"],
          k.section_names())
    k.section("mode", "MODE2", order=10)
    check("同名段覆盖不重复", k.compose_prompt("").count("MODE2") == 1
          and "MODE\n" not in k.compose_prompt(""))
    k.dispose()
    check("dispose 清理干净",
          not k.service_names() and not k.slot_names() and not k.section_names())


# ── 4. 插件装载与统一卸载 ────────────────────────────────────
class DemoPlugin(Plugin):
    name = "demo"
    inject = ("core",)

    def __init__(self):
        self.closed = False

    def apply(self, ctx):
        ctx.provide("demo.value", 99)
        ctx.section("demo", "DEMO_SECTION", order=20)
        ctx.slot("ui", "demo", "DEMO_WIDGET")
        ctx.on("ping", lambda p: None)

    def shutdown(self):
        self.closed = True


def test_plugins():
    k = Kernel()
    k.provide("core", True)
    try:
        DemoPlugin().apply  # noqa: B018
        p = DemoPlugin()
        try:
            k.load(p)
        except Exception as exc:
            check("插件装载", False, str(exc))
            return
    except Exception as exc:
        check("插件装载", False, str(exc))
        return
    check("插件服务已注册", k.get("demo.value") == 99)
    check("插件提示词段已注册", "demo" in k.section_names())
    check("插件槽位已注册", k.contributions("ui") == ["DEMO_WIDGET"])
    check("插件监听者已注册", k.has_listeners("ping"))
    check("插件名可枚举", k.plugin_names() == ["demo"])
    k.unload("demo")
    check("卸载后服务清除", k.get("demo.value") is None)
    check("卸载后段清除", "demo" not in k.section_names())
    check("卸载后槽位清除", k.contributions("ui") == [])
    check("卸载后监听者清除", not k.has_listeners("ping"))
    check("卸载调用 shutdown", p.closed)
    check("重复卸载返回 False", k.unload("demo") is False)
    k.dispose()


# ── 5. 模型注册表 ────────────────────────────────────────────
def test_models():
    tmp = tempfile.mkdtemp(prefix="miniagent_models_")
    target = os.path.join(tmp, "config.json")
    cfg = cfg_with({"provider": "mock", "model": "演示模式",
                    "api_base": "", "api_key": ""})
    reg = ModelRegistry(cfg, config_path=target)
    check("旧配置自动包装成一条默认模型", reg.catalog()["count"] == 1,
          reg.catalog())
    check("默认模型 id", reg.active_id() == "default")
    check("默认模型 provider", reg.active()["provider"] == "mock")

    cfg2 = cfg_with({
        "provider": "mock", "model": "演示模式", "api_base": "", "api_key": "",
        "models": [
            {"id": "local", "label": "本地", "provider": "ollama",
             "model": "qwen2.5:7b", "api_base": "http://127.0.0.1:11434"},
            {"id": "cloud", "label": "云端", "provider": "deepseek",
             "model": "deepseek-chat", "api_base": "https://api.deepseek.com/v1",
             "api_key": "SECRET-123"},
        ],
        "active_model": "local",
    })
    # 未传显式路径时也应跟随 cfg.path，而不是回落到用户真实目录
    cfg2.path = target
    reg3 = ModelRegistry(cfg2)
    check("注册表跟随 cfg.path", reg3.config_path == target, reg3.config_path)

    reg2 = ModelRegistry(cfg2, config_path=target)
    check("多模型目录条目数", reg2.catalog()["count"] == 2, reg2.catalog())
    check("provider 别名归一化", reg2.get("cloud")["provider"] == "openai_compat")
    check("当前生效模型", reg2.active_id() == "local")
    check("目录不回显 Key 明文",
          all("api_key" not in m for m in reg2.catalog()["models"]))
    cloud_pub = [m for m in reg2.catalog()["models"] if m["id"] == "cloud"][0]
    check("目录用 has_key 标记", cloud_pub["has_key"] is True)
    check("分组目录", len(reg2.list_providers()) == 2)

    view = reg2.resolve("cloud")
    check("配置视图覆盖模型字段", view.get("model") == "deepseek-chat")
    check("配置视图覆盖 Key", view.get("api_key") == "SECRET-123")
    check("配置视图回落基础配置", view.get("temperature") == 0.3)

    # 写操作全部落到临时目录，绝不碰用户真实配置
    r = reg2.set_active("cloud")
    check("切换到云端模型", r["ok"] and reg2.active_id() == "cloud")
    check("写操作落在临时目录", os.path.isfile(target), target)
    check("切换同步顶层标量", cfg2.get("model") == "deepseek-chat"
          and cfg2.get("api_key") == "SECRET-123")
    r = reg2.upsert({"id": "local", "provider": "ollama",
                     "model": "qwen2.5:14b"})
    check("编辑非当前模型不改生效配置",
          r["ok"] and cfg2.get("model") == "deepseek-chat", cfg2.get("model"))
    check("编辑生效", reg2.get("local")["model"] == "qwen2.5:14b")
    r = reg2.upsert({"id": "bad id!", "provider": "x", "model": "m"})
    check("非法 id / provider 被拒绝", not r["ok"])
    r = reg2.remove("local")
    check("删除模型", r["ok"] and reg2.catalog()["count"] == 1)
    r = reg2.remove("cloud")
    check("至少保留一个模型", not r["ok"])
    check("停用当前模型会自动改选",
          reg2.toggle("cloud", False)["ok"] and reg2.active_id() != "cloud")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


# ── 6. 模式 ──────────────────────────────────────────────────
def test_mode():
    check("四档模式", mode_ids() == ["minimal", "standard", "code", "creator"])
    check("非法模式回退默认", normalize_mode("nope") == "standard")
    check("模式目录标记当前", mode_catalog("code")["active"] == "code")


# ── 7. Runtime 端到端：多模型切换 + 内核接线 ─────────────────
def test_runtime():
    tmp = tempfile.mkdtemp(prefix="miniagent_rt_")
    cfg = cfg_with({
        "provider": "mock", "model": "演示模式", "api_base": "", "api_key": "",
        "mcpServers": {}, "plugins_dir": "plugins", "skills_dir": "skills",
        "workspace": tmp, "stream": False, "auto_confirm": True,
        "models": [
            {"id": "demo", "label": "演示", "provider": "mock",
             "model": "演示模式", "api_base": ""},
            {"id": "demo2", "label": "演示二", "provider": "mock",
             "model": "演示模式二", "api_base": ""},
        ],
        "active_model": "demo",
    })
    rt = Runtime(cfg, home=tmp, llm_script=None)
    agent = rt.build()
    check("内核服务已装配", "models" in rt.kernel.service_names())
    check("Agent 已挂内核", agent.kernel is rt.kernel)
    check("内核有基础人格段", "persona" in rt.kernel.section_names())
    check("模式段已登记", any(s.startswith("mode.") for s in rt.kernel.section_names()))
    check("内核服务含 llm/agent",
          "llm" in rt.kernel.service_names() and "agent" in rt.kernel.service_names())

    r = rt.use_model("demo2")
    check("运行时切换模型", r["ok"] and rt.models.active_id() == "demo2")
    check("切换后 Agent 后端同步", agent.llm is rt.llm)
    check("切换后顶层标量同步", cfg.get("model") == "演示模式二")

    r = rt.set_mode("code")
    check("运行时切换模式", r["ok"] and rt.mode == "code")
    check("模式改变步数上限", agent.max_steps == 32, agent.max_steps)
    check("模式段已更新", "mode.code" in rt.kernel.section_names())
    check("提示词包含模式说明", "当前模式：编程" in agent.system_prompt())

    # 事件链拦截：插件可以改写本轮使用的后端
    marker = []
    def intercept(payload, nxt):
        marker.append(payload["input"])
        return nxt(payload)
    rt.kernel.on(EVENT_REQUEST, intercept, prepend=True)
    out = agent.chat("你好", stream=False)
    check("请求事件链被触发", marker == ["你好"], marker)
    check("对话仍可完成", isinstance(out, str) and len(out) > 0, out)

    status = rt.status()
    check("状态含模型目录", "模型目录: 2 个" in status, status)
    check("内核状态结构完整",
          set(rt.kernel_status().keys()) == {"services", "sections", "slots", "plugins"})
    rt.shutdown()
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_services()
    test_events()
    test_scope_sections_slots()
    test_plugins()
    test_models()
    test_mode()
    test_runtime()
    print("\n%d 项通过, %d 项失败" % (PASS[0], FAIL[0]))
    return 1 if FAIL[0] else 0


if __name__ == "__main__":
    sys.exit(main())
