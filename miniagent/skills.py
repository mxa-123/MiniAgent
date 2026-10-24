# -*- coding: utf-8 -*-
"""技能系统：一个 .md 文件 = 一个技能（YAML frontmatter + 指令正文）。

约定（与主流 Agent 一致的极简版）：
    ---
    name: 代码审查
    description: 审查 Python 代码并给出修改清单
    ---
    正文：模型加载后要遵守的指令 / 步骤 / 示例
"""

from __future__ import annotations

import io
import os
import re
from typing import Dict, List, Optional

from .tools import tool
from .util import LOG, read_text

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


class Skill(object):
    def __init__(self, name: str, description: str, body: str, path: str):
        self.name = name
        self.description = description
        self.body = body
        self.path = path

    def __repr__(self) -> str:  # pragma: no cover
        return "<Skill %s>" % self.name


class Skills(object):
    def __init__(self, directory: str):
        self.directory = os.path.abspath(directory) if directory else ""
        self._skills: Dict[str, Skill] = {}

    def load(self) -> int:
        self._skills = {}
        if not self.directory or not os.path.isdir(self.directory):
            LOG.info("技能目录不存在: %s", self.directory)
            return 0
        for fn in sorted(os.listdir(self.directory)):
            if not fn.lower().endswith((".md", ".markdown")):
                continue
            path = os.path.join(self.directory, fn)
            try:
                skill = parse_skill(read_text(path), path)
                self._skills[skill.name] = skill
            except Exception as exc:
                LOG.warning("技能 %s 解析失败: %s", fn, exc)
        LOG.info("已加载 %d 个技能", len(self._skills))
        return len(self._skills)

    def names(self) -> List[str]:
        return sorted(self._skills.keys())

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def catalog(self) -> str:
        if not self._skills:
            return ""
        return "\n".join("- %s: %s" % (n, s.description) for n, s in sorted(self._skills.items()))

    def register_tool(self, registry, agent=None) -> None:
        """注册 use_skill 工具：模型按需加载技能正文。"""
        skills = self

        @tool(description="加载指定技能的详细指令（先看 /skills 列表再用）")
        def use_skill(name: str) -> str:
            """按名称加载技能正文。
            :param name: 技能名称
            """
            s = skills.get(name)
            if not s:
                return "没有这个技能: %s。可用: %s" % (name, ", ".join(skills.names()) or "（空）")
            return "# 技能: %s\n\n%s" % (s.name, s.body)

        registry.register_func(use_skill, source="skill")


def parse_skill(text: str, path: str = "") -> Skill:
    name = os.path.splitext(os.path.basename(path))[0] if path else "skill"
    description = ""
    body = text or ""
    m = _FM_RE.match(text or "")
    if m:
        meta_raw, body = m.group(1), m.group(2)
        meta: Dict[str, str] = {}
        for line in meta_raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        name = meta.get("name") or name
        description = meta.get("description", "")
    body = body.strip()
    if not description:
        first = body.splitlines()[0] if body else ""
        description = first[:120]
    return Skill(name=name, description=description, body=body, path=path)
