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

    # 2) 建总调度器（记忆在 Orchestrator 内部，多轮共用）
    orch = Orchestrator()

    # 3) 交互模式：python main.py --chat 进入多轮对话，记忆跨轮保留
    if "--chat" in sys.argv:
        print("💬 进入多轮对话（输入空行或 exit 退出，输入 /reset 清空记忆）：")
        while True:
            try:
                q = input("\n你> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q:
                continue
            if q in ("/reset", "/新对话"):
                orch.memory.reset()
                print("🧹 已清空对话记忆。")
                continue
            if q in ("exit", "quit"):
                break
            print(f"💡 {orch.handle(q)}")
        return

    # 4) 单次/批量模式：命令行传了就用传的，否则用两个示例（记忆在两问间保留）
    if len(sys.argv) > 1 and sys.argv[1] != "--chat":
        questions = [sys.argv[1]]
    else:
        questions = [
            "上月销售额最高的商品是哪个？",          # → 走 ReAct + 智能问数
            "那它的销售额占全公司多少比例？",         # → 同一会话追问，验证记忆/指代消解
        ]

    for q in questions:
        print("\n" + "=" * 60)
        print(f"❓ 用户问题：{q}")
        answer = orch.handle(q)
        print(f"💡 最终回答：\n{answer}")


if __name__ == "__main__":
    main()
