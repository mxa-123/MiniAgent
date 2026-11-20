# -*- coding: utf-8 -*-
"""新手引导层单测：不联网、不写真实用户目录。

运行： python tests/test_onboarding.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from miniagent.config import ENV_MAP, Config  # noqa: E402
import miniagent.onboarding as ob  # noqa: E402

PASS = []
FAIL = []


def check(name, cond):
    if cond:
        PASS.append(name)
    else:
        FAIL.append(name)


class _TmpHome(object):
    """把向导的配置输出重定向到临时目录，绝不碰真实 ~/.miniagent。"""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="miniagent_onboard_")
        self.old = ob.DEFAULT_HOME

    def __enter__(self):
        ob.DEFAULT_HOME = self.dir
        return self.dir

    def __exit__(self, *args):
        ob.DEFAULT_HOME = self.old
        shutil.rmtree(self.dir, ignore_errors=True)


def main():
    # 环境变量会覆盖配置，测试前清掉，保证结果稳定
    for env_key in ENV_MAP:
        os.environ.pop(env_key, None)

    with _TmpHome() as tmp:
        cfg = Config({"provider": "openai_compat", "model": "deepseek-chat",
                      "api_base": "https://api.deepseek.com/v1", "api_key": ""})
        state = ob.check_setup(cfg)
        check("默认状态为未配置", state["configured"] is False)
        check("状态不回显 API Key", "api_key" not in state)
        check("提供三个模型来源", len(state["presets"]) == 3)
        check("示例任务不少于 4 个", len(state["examples"]) >= 4)

        cfg.set("api_key", "在这里填你的 Key")
        check("占位符 Key 不算已配置", ob.check_setup(cfg)["configured"] is False)
        cfg.set("api_key", "")

        r = ob.apply_setup(cfg, {"preset": "demo"})
        check("演示模式一键保存成功", r["ok"] is True)
        check("演示模式保存后已就绪", ob.check_setup(cfg)["configured"] is True)
        path = os.path.join(tmp, "config.json")
        check("配置写到用户目录", os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        check("演示模式 provider 为 mock", saved.get("provider") == "mock")
        check("演示模式不残留 Key", not saved.get("api_key"))
        check("向导完成标记已写入", saved.get("onboarding", {}).get("done") is True)

        r2 = ob.apply_setup(cfg, {"preset": "cloud"})
        check("云端不填 Key 会被拒绝", r2["ok"] is False)
        check("被拒绝时给出人话原因", "API Key" in r2["message"])

        r3 = ob.apply_setup(cfg, {"preset": "cloud", "api_key": "sk-test-123"})
        check("云端填 Key 保存成功", r3["ok"] is True)
        s3 = ob.check_setup(cfg)
        check("云端配置后已就绪", s3["configured"] is True)
        check("只回显是否设置过 Key", s3["api_key_set"] is True)
        check("状态里不含完整 Key", "sk-test-123" not in json.dumps(s3, ensure_ascii=False))

        r4 = ob.apply_setup(cfg, {"preset": "cloud", "model": "deepseek-reasoner"})
        check("只改模型名不会丢掉 Key",
              r4["ok"] is True and cfg.get("api_key") == "sk-test-123")
        check("模型名确实更新了", cfg.get("model") == "deepseek-reasoner")

        check("拒绝未知 provider", ob.validate_setup({"provider": "evil"})[0] is False)
        check("拒绝非法服务地址", ob.validate_setup({"api_base": "ftp://x"})[0] is False)
        check("空表单合法", ob.validate_setup({})[0] is True)

    check("读取文件说人话", "正在读取文件" in ob.friendly_tool("read_file", {"path": "a.txt"}))
    check("联网搜索说人话", "正在联网搜索" in ob.friendly_tool("web_search", {"query": "天气"}))
    check("未知工具兜底", "正在使用工具" in ob.friendly_tool("xyz_tool", {}))

    e1 = ob.humanize_error("HTTP 401 Unauthorized")
    check("401 提示检查 Key", "Key" in e1["title"] and e1["action"] == "setup")
    e2 = ob.humanize_error("Read timed out")
    check("超时提示可重试", e2["action"] in ("retry", "network"))
    e3 = ob.humanize_error("Connection refused", "ollama")
    check("Ollama 连不上提示启动服务", "Ollama" in e3["title"])

    mock_cfg = Config({"provider": "mock", "api_base": "", "api_key": ""})
    check("演示模式连接自检不联网", ob.test_connection(mock_cfg)["ok"] is True)

    print("PASS %d 项" % len(PASS))
    for name in FAIL:
        print("FAIL " + name)
    if FAIL:
        print("\n%d 项失败" % len(FAIL))
        return 1
    print("全部通过：新手引导层")
    return 0


if __name__ == "__main__":
    sys.exit(main())
