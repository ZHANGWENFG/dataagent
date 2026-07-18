# -*- coding: utf-8 -*-
"""
main.py —— 命令行入口（大白话版）
================================
跑法：
    cd simple_data_agent
    python main.py            # 会用内置的两个示例问题演示整条链路
    python main.py "你的问题"  # 也可以自己传一个问题

前置：先在终端设置好 LLM 环境变量（详见 README.md）
    export OPENAI_API_KEY=sk-xxx
    export OPENAI_BASE_URL=https://api.openai.com/v1
    export MODEL=gpt-4o-mini
"""

import sys
from db import build
from agent import Orchestrator


def main():
    # 1) 先确保示例数据库存在（第一次跑会建库+灌数据）
    build()

    # 2) 建总调度器
    orch = Orchestrator()

    # 3) 决定跑哪个问题：命令行传了就用传的，否则用两个示例
    if len(sys.argv) > 1:
        questions = [sys.argv[1]]
    else:
        questions = [
            "上月销售额最高的商品是哪个？",          # → 走 ReAct + 智能问数
            "分析一下最近半年销售额的异常和原因。",   # → 走 Plan-and-Execute + 诊断
        ]

    for q in questions:
        print("\n" + "=" * 60)
        print(f"❓ 用户问题：{q}")
        answer = orch.handle(q)
        print(f"💡 最终回答：\n{answer}")


if __name__ == "__main__":
    main()
