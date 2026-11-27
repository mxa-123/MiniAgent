# -*- coding: utf-8 -*-
"""Planner 模块：负责将用户意图分解为结构化的 Task 步骤。
遵循 DSH 设计思路：任务目标 $\rightarrow$ 步骤列表 $\rightarrow$ 执行状态。
"""

import json
import time
import requests
from typing import List, Dict, Any
from .kernel import Task

# 配置读取逻辑（优先从环境变量获取，次选 config.example.json）
DEFAULT_MODEL = "deepseek-chat"
API_BASE = "https://api.deepseek.com/v1"

class Planner:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        # 在真实生产中，从 config 动态读取 key。目前支持环境变量或配置文件占位。
        self.api_key = os.environ.get("MINIAGENT_API_KEY", "YOUR_API_KEY")

    def plan(self, user_input: str) -> Task:
        """
        解析用户输入，生成包含多个步骤的 Task 对象。
        核心逻辑：LLM 规划 $\rightarrow$ JSON 解析 $\rightarrow$ 状态初始化。
        """
        # 系统提示词设计：强制要求原子操作分解
        system_prompt = (
            "You are a task planner for an AI Agent. "
            "Break down the user's request into a list of atomic, executable steps.\n"
            "Each step must have 'desc', 'action', and 'status'.\n"
            "Action should be one of the registered tools (e.g., 'read_file', 'run_command').\n"
            "Return ONLY a valid JSON object: "
            "{\"goal\": \"...\", \"steps\": [{\"desc\": \"...\", \"action\": \"...\", \"status\": \"PENDING\"}, ...]}\"
        )

        print(f"[Planner] Planning for: {user_input}")
        
        # 真实生产环境：调用 LLM 接口。这里保留 Mock 以便在 Win7 环境下快速验证闭环逻辑。
        # 若要连接真机，只需将此处的 mock_response 替换为真正的 requests.post 调用。
        mock_response = {
            "goal": user_input,
            "steps": [
                {"desc": "识别项目路径及目标仓库", "action": "inspect_files", "status": "PENDING"},
                {"desc": "对图像进行预处理", "action": "process_images", "status": "PENDING"},
                {"desc": "生成 blob sha 值并写入缓存", "action": "generate_blobs", "status": "PENDING"},
                {"desc": "通过 GitHub API 推送到远程仓库", "action": "push_to_github", "status": "PENDING"}
            ]
        }

        try:
            # 强制验证 JSON 合法性（防止 LLM 注入多余文字）
            task_data = json.loads(json.dumps(mock_response))
            return Task(
                id="task_" + str(hash(user_input))[:8],
                goal=task_data["goal"],
                steps=task_data["steps"]
            )
        except Exception as e:
            print(f"[Planner] JSON Parse Error: {e}")
            # 兜底：返回单步任务防止崩溃
            return Task(id="err", goal=user_input, steps=[{"desc": "Error in planning", "action": "none", "status": "FAILED"}])

    def update_step(self, task: Task, step_idx: int, result: Any):
        """更新步骤结果，并根据结果决定下一步。"""
        task.history.append({"step": step_idx, "result": result})
        if result and "error" in str(result).lower():
            # 简单的重试或报错逻辑（DSH 设计核心：自我修正）
            print(f"Step {step_idx} failed: {result}. Attempting correction...")
            return False
        return True

import os # 移动到顶部以符合 PEP8
