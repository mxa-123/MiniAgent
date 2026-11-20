# -*- coding: utf-8 -*-
"""模型注册表：把「单个模型标量配置」升级成「可管理多个模型的目录」。

设计灵感来自插件化架构里「模型是可插拔路由」的思路（参考开源项目 DeepSeek Harness 的公开设计思路；对方许可证以其仓库声明为准）。
本文件为独立实现，未使用、未复制任何第三方项目源码。

兼容性（重要）：
  - 旧配置只有 provider / model / api_base / api_key 四个标量；
    注册表会自动把它们包装成一条 id="default" 的模型，行为完全不变。
  - 新配置用 models: [ {id, label, provider, model, api_base, api_key, enabled} ]
    + active_model: "<id>"。
  - 无论新旧，顶层四个标量始终表示「当前生效模型」，写入配置时同步刷新，
    这样 CLI 的 --model、环境变量、老代码路径都不需要改。

安全：对外输出目录时不回显完整 API Key，只给 has_key 布尔；配置只写用户目录。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from .config import DEFAULT_HOME

# 一条模型允许出现的字段白名单（防写入任意配置键）
MODEL_FIELDS = ("id", "label", "provider", "model", "api_base", "api_key", "enabled")
ALLOWED_PROVIDERS = ("mock", "ollama", "openai_compat")

# create_llm 历来接受的别名，统一归一化到三个标准来源
_PROVIDER_ALIASES = {
    "openai": "openai_compat",
    "compat": "openai_compat",
    "deepseek": "openai_compat",
    "openai_compat": "openai_compat",
    "ollama": "ollama",
    "ollama_native": "ollama",
    "mock": "mock",
}

# id 只允许字母数字 / 点 / 短横 / 下划线，避免拿它拼路径或当命令参数
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,48}$")


class ModelConfigView(object):
    """把某条模型覆盖到基础配置上的只读视图，可直接传给 create_llm。

    只覆盖模型相关字段，其余（temperature / timeout / max_tokens ...）沿用基础配置。
    """

    _OVERLAY = ("provider", "model", "api_base", "api_key")

    def __init__(self, cfg: Any, entry: Dict[str, Any]):
        self._cfg = cfg
        self._entry = entry

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._OVERLAY and key in self._entry:
            return self._entry.get(key)
        return self._cfg.get(key, default)

    def set(self, key: str, value: Any) -> None:
        # 视图只读：改配置请走 ModelRegistry / Config 本身
        raise AttributeError("ModelConfigView 是只读视图")


class ModelRegistry(object):
    """模型目录 + 当前生效模型。所有写操作落到 cfg，并保存到 config_path。

    config_path 由 Runtime 传入（跟随 rt.home）。测试/自定义 --home 时会写进
    临时目录，不会污染用户真实的 ~/.miniagent/config.json。
    即便独立使用、未传显式路径，也会优先跟随 cfg 自身携带的路径信息。
    """

    def __init__(self, cfg: Any, config_path: Optional[str] = None):
        self.cfg = cfg
        self.config_path = self._resolve_path(cfg, config_path)
        self._entries: List[Dict[str, Any]] = []
        self._reload()

    @staticmethod
    def _resolve_path(cfg: Any, config_path: Optional[str]) -> str:
        """决定落盘位置：显式参数 > cfg.config_target > cfg.path > 用户默认目录。

        显式参数由 Runtime 传入（跟随 rt.home）；后两者让独立使用注册表时
        也跟着 Config 走，避免测试 / 脚本把数据写进用户真实配置。
        """
        for candidate in (config_path,
                          getattr(cfg, "config_target", None),
                          getattr(cfg, "path", None)):
            if candidate:
                s = str(candidate).strip()
                if s:
                    return s
        return os.path.join(DEFAULT_HOME, "config.json")

    # ── 读取 / 规范化 ──────────────────────────────────────────
    def _reload(self) -> None:
        raw = self.cfg.get("models", [])
        entries: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                norm = self._normalize(item)
                if norm:
                    entries.append(norm)
        if not entries:
            # 旧配置兼容：把四个标量包装成一条默认模型
            legacy = {
                "id": "default",
                "label": str(self.cfg.get("model", "") or "默认模型"),
                "provider": str(self.cfg.get("provider", "openai_compat") or "openai_compat"),
                "model": str(self.cfg.get("model", "") or ""),
                "api_base": str(self.cfg.get("api_base", "") or ""),
                "api_key": str(self.cfg.get("api_key", "") or ""),
                "enabled": True,
            }
            if legacy["model"]:
                entries.append(legacy)
        # 去重（同 id 保留最后一条）
        seen: Dict[str, Dict[str, Any]] = {}
        for e in entries:
            seen[e["id"]] = e
        self._entries = [seen[k] for k in sorted(seen.keys())]

    @staticmethod
    def _normalize(item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        mid = str(item.get("id", "") or "").strip()
        raw_provider = str(item.get("provider", "") or "").strip().lower()
        provider = _PROVIDER_ALIASES.get(raw_provider, "")
        model = str(item.get("model", "") or "").strip()
        if not _ID_RE.match(mid) or not model:
            return None
        if raw_provider and not provider:
            return None
        out = {
            "id": mid,
            "label": str(item.get("label", "") or "").strip() or mid,
            "provider": provider or "openai_compat",
            "model": model,
            "api_base": str(item.get("api_base", "") or "").strip(),
            "api_key": str(item.get("api_key", "") or ""),
            "enabled": bool(item.get("enabled", True)),
        }
        base = out["api_base"]
        if base and not (base.startswith("http://") or base.startswith("https://")):
            return None
        return out

    # ── 查询 ──────────────────────────────────────────────────
    def entries(self) -> List[Dict[str, Any]]:
        return [dict(e) for e in self._entries]

    def ids(self) -> List[str]:
        return [e["id"] for e in self._entries]

    def get(self, mid: str) -> Optional[Dict[str, Any]]:
        for e in self._entries:
            if e["id"] == mid:
                return dict(e)
        return None

    def active_id(self) -> str:
        want = str(self.cfg.get("active_model", "") or "").strip()
        if want and any(e["id"] == want and e["enabled"] for e in self._entries):
            return want
        for e in self._entries:
            if e["enabled"]:
                return e["id"]
        return ""

    def active(self) -> Optional[Dict[str, Any]]:
        mid = self.active_id()
        return self.get(mid) if mid else None

    def resolve(self, mid: Optional[str] = None) -> Optional[ModelConfigView]:
        """取一条模型的配置视图；mid 为空则取当前生效模型。"""
        entry = self.get(mid) if mid else self.active()
        if not entry:
            return None
        return ModelConfigView(self.cfg, entry)

    def list_providers(self) -> List[Dict[str, Any]]:
        """按来源分组的目录，供界面渲染（不回显 Key）。"""
        groups: Dict[str, Dict[str, Any]] = {}
        for e in self._entries:
            p = e["provider"]
            if p not in groups:
                groups[p] = {"provider": p, "label": _PROVIDER_LABELS.get(p, p),
                             "models": []}
            groups[p]["models"].append(self.public(e))
        return [groups[k] for k in sorted(groups.keys())]

    def list_models(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for e in self._entries:
            if provider and e["provider"] != provider:
                continue
            out.append(self.public(e))
        return out

    @staticmethod
    def public(entry: Dict[str, Any]) -> Dict[str, Any]:
        """对外输出：抹掉 API Key 明文，只保留是否设置过。"""
        return {
            "id": entry["id"],
            "label": entry["label"],
            "provider": entry["provider"],
            "model": entry["model"],
            "api_base": entry["api_base"],
            "has_key": bool(entry.get("api_key")),
            "enabled": bool(entry.get("enabled", True)),
            "active": False,  # 由 catalog() 填
        }

    def catalog(self) -> Dict[str, Any]:
        """给界面的完整快照。"""
        cur = self.active_id()
        models = []
        for e in self._entries:
            p = self.public(e)
            p["active"] = (e["id"] == cur)
            models.append(p)
        return {
            "active_model": cur,
            "models": models,
            "providers": self.list_providers(),
            "count": len(models),
            "config_path": self.config_path,
        }

    # ── 写操作 ────────────────────────────────────────────────
    def _flush(self) -> None:
        """只写回模型目录本身。

        顶层四个标量代表「当前生效模型」，只在 active 真正变化时才同步，
        否则编辑/停用一条非当前模型会误改正在用的配置。
        """
        self.cfg.set("models", self.entries())

    def _sync_scalars(self) -> None:
        """把当前生效模型同步到顶层标量，保持 CLI/环境变量等旧路径可用。"""
        cur = self.active()
        if cur:
            for k in ("provider", "model", "api_base", "api_key"):
                self.cfg.set(k, cur.get(k, ""))
            self.cfg.set("active_model", cur["id"])

    def set_active(self, mid: str) -> Dict[str, Any]:
        entry = self.get(mid)
        if not entry:
            return {"ok": False, "message": "没有这个模型：%s" % mid}
        if not entry.get("enabled", True):
            return {"ok": False, "message": "这个模型已停用，先启用再切换"}
        self.cfg.set("active_model", mid)
        self._flush()
        self._sync_scalars()
        self.cfg.save(self.config_path)
        return {"ok": True, "message": "已切换到 %s（%s）" % (entry["label"], entry["model"]),
                "catalog": self.catalog()}

    def upsert(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """新增或修改一条模型。api_key 留空表示「不修改已保存的 Key」。"""
        norm = self._normalize(item)
        if not norm:
            return {"ok": False, "message": "模型信息不完整：需要合法的 id、provider 和模型名"}
        existing = self.get(norm["id"])
        if existing and not norm.get("api_key"):
            norm["api_key"] = existing.get("api_key", "")
        replaced = False
        for i, e in enumerate(self._entries):
            if e["id"] == norm["id"]:
                self._entries[i] = norm
                replaced = True
                break
        if not replaced:
            self._entries.append(norm)
        self._entries.sort(key=lambda e: e["id"])
        self._flush()
        # 编辑的正是当前生效模型时，把改动同步到顶层标量
        if norm["id"] == self.active_id():
            self._sync_scalars()
        self.cfg.save(self.config_path)
        return {"ok": True, "message": "已保存模型 %s" % norm["label"],
                "catalog": self.catalog()}

    def remove(self, mid: str) -> Dict[str, Any]:
        if not self.get(mid):
            return {"ok": False, "message": "没有这个模型：%s" % mid}
        if len(self._entries) <= 1:
            return {"ok": False, "message": "至少保留一个模型"}
        was_active = (self.active_id() == mid)
        self._entries = [e for e in self._entries if e["id"] != mid]
        if was_active:
            self.cfg.set("active_model", "")
        self._flush()
        self._sync_scalars()
        self.cfg.save(self.config_path)
        return {"ok": True, "message": "已删除模型 %s" % mid,
                "catalog": self.catalog()}

    def toggle(self, mid: str, enabled: bool) -> Dict[str, Any]:
        entry = self.get(mid)
        if not entry:
            return {"ok": False, "message": "没有这个模型：%s" % mid}
        was_active = (self.active_id() == mid)
        for e in self._entries:
            if e["id"] == mid:
                e["enabled"] = bool(enabled)
        if not enabled and was_active:
            self.cfg.set("active_model", "")
        self._flush()
        self._sync_scalars()
        self.cfg.save(self.config_path)
        return {"ok": True, "message": "已%s %s" % ("启用" if enabled else "停用", mid),
                "catalog": self.catalog()}

    def refresh(self) -> None:
        self._reload()


_PROVIDER_LABELS = {
    "mock": "演示模式（不联网）",
    "ollama": "本地模型（Ollama）",
    "openai_compat": "云端 / 兼容接口",
}
