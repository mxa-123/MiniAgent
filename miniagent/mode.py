# -*- coding: utf-8 -*-
"""运行时模式预设：把「四档深度可调」做成一组可切换的配置组合。

设计灵感来自插件化框架中「运行时模式」的分层思想（参考开源项目 DeepSeek Harness 的公开设计思路；对方许可证以其仓库声明为准）。
本文件为独立实现，未复制任何第三方源码或文案。

模式只影响三样东西：推理步数上限、系统提示词附加段、工具裁剪。
切换模式不写文件（临时生效），除非显式保存配置。
"""

from __future__ import annotations

from typing import Any, Dict, List

# order 越小越靠前；段名带前缀，避免与插件自己的段冲突
MODES: Dict[str, Dict[str, Any]] = {
    "minimal": {
        "label": "极简",
        "summary": "少绕路、省额度，适合简单问答",
        "max_steps": 6,
        "sections": [("mode.minimal", 10,
                      "## 当前模式：极简\n直接给结论，能一步做完就别拆成多步；"
                      "非必要不调用工具。")],
        "exclude_tools": (),
    },
    "standard": {
        "label": "标准",
        "summary": "默认档，工具与步数平衡",
        "max_steps": 24,
        "sections": [("mode.standard", 10,
                      "## 当前模式：标准\n需要事实时先调用工具拿到结果再回答，"
                      "步骤尽量精简。")],
        "exclude_tools": (),
    },
    "code": {
        "label": "编程",
        "summary": "允许多步调试，优先看文件与运行结果",
        "max_steps": 32,
        "sections": [("mode.code", 10,
                      "## 当前模式：编程\n先读现有代码再动手改；每次改动后用工具"
                      "验证结果；给出可复制的完整代码，并说明怎么运行。")],
        "exclude_tools": (),
    },
    "creator": {
        "label": "创作",
        "summary": "放开步数，适合长文与多轮打磨",
        "max_steps": 40,
        "sections": [("mode.creator", 10,
                      "## 当前模式：创作\n可以分多轮推进：先列提纲，再逐段展开，"
                      "最后自己通读一遍并润色。")],
        "exclude_tools": (),
    },
}

DEFAULT_MODE = "standard"


def mode_ids() -> List[str]:
    return ["minimal", "standard", "code", "creator"]


def normalize_mode(name: str) -> str:
    key = str(name or "").strip().lower()
    return key if key in MODES else DEFAULT_MODE


def mode_info(name: str) -> Dict[str, Any]:
    key = normalize_mode(name)
    m = MODES[key]
    return {"id": key, "label": m["label"], "summary": m["summary"],
            "max_steps": m["max_steps"]}


def mode_catalog(current: str) -> Dict[str, Any]:
    cur = normalize_mode(current)
    items = []
    for mid in mode_ids():
        info = mode_info(mid)
        info["active"] = (mid == cur)
        items.append(info)
    return {"active": cur, "modes": items}


def apply_mode(kernel: Any, cfg: Any, name: str) -> str:
    """把模式应用到内核（提示词段）与配置（步数），返回生效的模式 id。

    反复调用安全：同名段会被覆盖，不会重复堆叠。
    """
    key = normalize_mode(name)
    m = MODES[key]
    if kernel is not None:
        for sec_name, order, text in m["sections"]:
            kernel.section(sec_name, text, order=order)
    cfg.set("max_steps", m["max_steps"])
    return key
