# -*- coding: utf-8 -*-
"""
agent.py —— 多 Agent 编排 harness（大白话版）
============================================
对标 joyagent 的后端框架（BaseAgent / ReActAgent / PlanningAgent / ExecutorAgent）。
这里把它的核心思想浓缩成"能跑的最小版"：

  BaseAgent    ：所有 Agent 的父类，管"记忆 + 工具 + 主循环"
  ReActAgent   ：单步 think→act 循环（适合简单问数）
  PlanningAgent：先出计划，再分步执行（适合"分析一下"这类多步任务）
  Orchestrator ：总调度，根据问题类型选 Skill + 选 Agent 模式
"""

import re
from llm import ask
from tools import ToolCollection
from skills import SKILLS, pick_skill


class BaseAgent:
    """
    所有 Agent 的基类。负责两件事：
    1) memory：对话历史（List[dict]，角色 user/assistant/tool）
    2) run()：主循环——反复"想一下 → 决定调哪个工具 → 执行 → 看结果"，直到能回答
    """

    def __init__(self, tools: ToolCollection, max_steps: int = 5):
        self.tools = tools
        self.memory = []          # 记忆：[{role, content}]
        self.max_steps = max_steps

    def _think(self, query: str) -> str:
        """让 LLM 决定'下一步调什么工具'。这里用最简单的文本协议：
        模型如果回 'CALL:工具名|参数'，就认为是调工具；否则当作最终答案。"""
        tool_list = self.tools.describe_for_llm()
        sys = ("你是调度器。可用工具：\n" + tool_list +
               "\n如需调工具，只回复 CALL:工具名|参数 ；否则直接给最终答案。")
        return ask(f"历史：{self.memory}\n当前问题：{query}", system=sys, temperature=0.0)

    def _act(self, decision: str, query: str) -> str:
        """解析模型决策：要调工具就调，拿结果写回记忆。"""
        m = re.match(r"CALL:(\w+)\|(.*)", decision.strip())
        if m:
            name, arg = m.group(1), m.group(2)
            tool = self.tools.get(name)
            if not tool:
                return f"未知工具：{name}"
            result = tool.run(query=arg) if "query" in tool.params else tool.run()
            self.memory.append({"role": "tool", "content": f"{name} 返回：{result}"})
            return result
        # 没让调工具 → 这就是最终答案
        self.memory.append({"role": "assistant", "content": decision})
        return decision

    def run(self, query: str) -> str:
        self.memory.append({"role": "user", "content": query})
        for step in range(self.max_steps):
            decision = self._think(query)
            out = self._act(decision, query)
            # 如果这一步已经产出最终答案（不在 CALL 协议里），就结束
            if not decision.strip().startswith("CALL:"):
                return out
        return "⚠️ 达到最大步数仍未得出结论（可增大 max_steps 或检查工具）。"


class ReActAgent(BaseAgent):
    """ReAct 模式：单步 think→act，上面 BaseAgent.run 就是这个行为，直接用即可。"""
    pass


class PlanningAgent(BaseAgent):
    """
    Plan-and-Execute 模式：先把任务拆成几步计划，再逐步执行（每步仍可调工具）。
    对标 joyagent 的 PlanningAgent + ExecutorAgent 组合，这里用顺序执行演示思想。
    """

    def run(self, query: str) -> str:
        self.memory.append({"role": "user", "content": query})
        # 1) 规划：让模型把大任务拆成有序小步骤
        plan = ask(f"请把这个任务拆成 2-4 个有序步骤：{query}",
                   system="你是规划师，只输出步骤列表，每步一行，不要执行。",
                   temperature=0.0)
        self.memory.append({"role": "assistant", "content": f"[计划]\n{plan}"})
        # 2) 执行：把每一步当作子问题，交给 ReAct 式循环逐个解决
        steps = [s for s in plan.splitlines() if s.strip() and not s.strip().startswith(("[", "#", "计划"))]
        for i, step in enumerate(steps, 1):
            sub = f"第{i}步：{step}（原目标：{query}）"
            decision = self._think(sub)
            self._act(decision, sub)
        # 3) 汇总：让模型基于全程记忆给最终答案
        return ask(f"基于以上执行过程，回答用户原问题：{query}",
                   system="你是总结者，给出最终结论。", temperature=0.2)


class Orchestrator:
    """
    总调度（对标 joyagent 的 AgentHandlerFactory）：
    1) 先按 Skill 路由，把相关技能说明注入上下文（这就是'技能系统'生效的地方）
    2) 再按问题类型选 Agent 模式：查数→ReAct，分析→Planning
    """

    def __init__(self):
        self.tools = ToolCollection()

    def handle(self, query: str) -> str:
        # —— 技能路由：选一份 SKILL.md 注入（可选）——
        skill = pick_skill(query, SKILLS)
        skill_hint = f"\n[参考技能]\n{skill}\n" if skill else ""

        # —— 模式选择：含'分析/为什么/原因/异常'→规划模式，否则 ReAct ——
        if any(k in query for k in ["分析", "为什么", "原因", "异常", "诊断"]):
            agent = PlanningAgent(self.tools)
            mode = "Plan-and-Execute"
        else:
            agent = ReActAgent(self.tools)
            mode = "ReAct"

        print(f"🧭 调度模式：{mode} ｜ 命中技能：{skill[:20] if skill else '无'}")
        answer = agent.run(query + skill_hint)
        return answer
