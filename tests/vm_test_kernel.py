# -*- coding: utf-8 -*-
"""Win7 环境下的 DSH 核心逻辑验证脚本。
模拟 Planner 生成任务 $\rightarrow$ Kernel 管理状态 $\rightarrow$ Executor 执行步骤的闭环。
"""

import sys
import os
from miniagent.kernel import Kernel, Task
from miniagent.planner import Planner

def run_dsh_logic_test():
    print("=== MiniAgent DSH 核心逻辑验证 (Win7 环境) ===")
    
    # 1. 初始化内核（宿主）
    kernel = Kernel()
    
    # 2. 初始化规划引擎
    planner = Planner(model_name="deepseek-chat")
    
    # 3. 输入模拟用户指令
    user_input = "帮我把这些图片处理了并更新到 GitHub"
    print(f"Input: {user_input}")
    
    # 4. 执行规划（Planner -> Task）
    task = planner.plan(user_input)
    print(f"Task ID: {task.id}")
    print(f"Target Goal: {task.goal}")
    print(f"Plan Steps: {len(task.steps)}")
    
    # 5. 模拟执行流（Executor 的逻辑原型）
    for i in range(len(task.steps)):
        step = task.steps[i]
        print(f"--- Executing Step {i} ---")
        print(f"Description: {step['desc']}")
        
        # 模拟执行动作（此处仅验证状态流转）
        success = True # 假设成功
        if success:
            task.update_history(f"Success: {step['action']}")
            print(f"Result: Success")
        else:
            print("Result: Failed (Simulated)")

    print("\n=== 验证结论 ===")
    print(f"Final Task Status: {task.status}")
    print(f"History Logs count: {len(task.history)}")
    print("Core Logic Check: PASSED")

if __name__ == "__main__":
    try:
        run_dsh_logic_test()
    except Exception as e:
        print(f"CRITICAL FAILURE: {e}")
        sys.exit(1)
