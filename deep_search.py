# -*- coding: utf-8 -*-
"""
deep_search.py —— 深度搜索 / 顺序多步推理闭环（大白话版）
========================================================
对标 joyagent 的 deepsearch.py：针对"复杂 / 根因 / 综合"类问题，
不像 PlanningAgent 那样"把子任务并行扇出一把梭"，而是走一个**顺序的多步推理闭环**：

  1) 拆解  ：把大问题拆成若干子问题（decompose）
  2) 检索  ：逐个子问题去调工具拿证据（evidence），每一步把结果写进"证据本"
  3) 反思  ：每攒够一轮，让模型判断"证据够不够回答原问题"；
             不够就让它再补几个子问题（loop 继续），够了才进第 4 步
  4) 综合  ：把所有证据拼起来，让模型写出最终答案

和 PlanningAgent 的区别（面试能讲清）：
  · PlanningAgent = 并行扇出，各子步互不依赖、一把跑完再汇总；
  · DeepSearch    = 顺序闭环，每步都能"看前面证据再决定下一步要查啥"，更接近人做调研。
"""

import re
from llm import ask
from tools import DataQueryTool, DiagnosticTool
from config import LLM_API_KEY


# ---------------- 默认工具箱：DeepSearch 默认能调哪些工具 ----------------
def _default_run_tool(tool_name: str, arg: str) -> str:
    """
    默认的工具执行器：把工具名映射到本地工具对象。
    DeepSearch 本身不关心"工具怎么实现"，只管"给名字+参数，拿回文本证据"。
    想接更多工具（比如知识库检索），只要在外面传一个自己的 run_tool 即可。
    """
    tools = {
        "data_query": DataQueryTool(),
        "diagnostic": DiagnosticTool(),
    }
    tool = tools.get(tool_name)
    if not tool:
        return f"[未知工具] {tool_name}"
    return tool.run(query=arg)


def _parse_steps(text: str) -> list:
    """把模型回的多行文本，清理成子问题列表（去掉空行 / 编号前缀 / 计划词）。"""
    steps = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # 去掉 "1." / "一、" / "- " 这类前缀
        s = re.sub(r"^(\d+[.、]|[一二三四五六七八九十]+[.、]|[-*]\s*)", "", s)
        if s and not s.startswith(("[", "#", "计划")):
            steps.append(s)
    return steps


def _decompose(query: str, evidence: str = "") -> list:
    """
    第 1 步：拆解。让模型把复杂问题拆成 2-4 个有序子问题。
    如果 evidence 非空（说明是在"反思后补查"），则让模型基于已有证据再补子问题。
    """
    if not evidence:
        sys = "你是研究规划师。把用户问题拆成 2-4 个有序子问题，每行一个，不要回答。"
        return _parse_steps(ask(f"请拆解这个复杂问题：{query}", system=sys, temperature=0.0))
    sys = ("你是研究规划师。下面是你已有的证据和未回答的问题，"
           "请再补 1-3 个子问题去补齐证据，每行一个。")
    return _parse_steps(ask(
        f"原问题：{query}\n已有证据：\n{evidence}\n还缺哪些证据？请补子问题：",
        system=sys, temperature=0.0))


def _plan_tool(sub: str) -> tuple:
    """
    第 2 步里的一环：让模型决定"这个子问题用哪个工具、参数怎么写"。
    返回 (工具名, 参数)。约定只回 '工具名|参数'，解析失败兜底成 data_query + 原问题。
    """
    sys = ("你是工具调度。可用工具：data_query(智能问数) / diagnostic(诊断分析)。"
           "只回 工具名|参数，不要解释。")
    plan = ask(
        f"子问题：{sub}\n请决定用哪个工具并给出参数。只回 '工具名|参数'：",
        system=sys, temperature=0.0)
    m = re.match(r"\s*(\w+)\s*\|(.*)", plan)
    if m:
        return m.group(1), m.group(2).strip()
    return "data_query", sub


def _reflect(query: str, evidence: str) -> str:
    """
    第 3 步：反思。让模型判断"现有证据够不够答原问题"。
    返回 "ENOUGH"（够了可以综合）或 "MORE:子问题1\n子问题2"（还不够，要再查）。
    """
    sys = ("你是严谨的研究评审。判断下面'已有证据'是否足以回答'原问题'。"
           "如果够了，只回 ENOUGH；如果不够，回 MORE: 然后列出还想查的 1-3 个子问题，每行一个。不要解释。")
    return ask(f"原问题：{query}\n已有证据：\n{evidence}", system=sys, temperature=0.0)


def _synthesize(query: str, evidence: str) -> str:
    """第 4 步：综合。把所有证据拼成最终答案。"""
    sys = "你是资深分析师。基于下面的证据，给出连贯、有依据的最终答案，关键结论要引用证据。"
    return ask(f"原问题：{query}\n证据汇总：\n{evidence}", system=sys, temperature=0.2)


def deep_search(query: str, run_tool=None, max_rounds: int = 3,
                max_steps_per_round: int = 4) -> dict:
    """
    深度搜索主入口：顺序多步推理闭环。
    :param query: 用户复杂问题
    :param run_tool: 工具执行器 (名字, 参数) -> 文本证据；不传用默认(_default_run_tool)
    :param max_rounds: 最多几轮"检索+反思"（防止无限循环）
    :param max_steps_per_round: 每轮最多查几个子问题
    :return: {steps, evidence, answer, rounds}
      - steps   ：收集到的所有"子问题→工具→证据"步骤（界面/调试用）
      - evidence：拼好的证据文本
      - answer  ：最终综合答案
      - rounds  ：实际跑了几轮
    """
    run_tool = run_tool or _default_run_tool

    raw = []               # 每一步的记录：{sub, tool, arg, result}
    evidence_parts = []    # 证据文本片段
    rounds = 0

    # 初始拆解
    todo = _decompose(query)
    if not todo:
        # 拆不动就直接综合（兜底）
        return {"steps": [], "evidence": "", "answer": _synthesize(query, ""), "rounds": 0}

    for r in range(max_rounds):
        rounds += 1
        # 这一轮：把当前 todo 的子问题逐个去查
        for sub in todo[:max_steps_per_round]:
            tool_name, tool_arg = _plan_tool(sub)
            result = run_tool(tool_name, tool_arg)
            raw.append({"sub": sub, "tool": tool_name, "arg": tool_arg, "result": result})
            evidence_parts.append(f"【子问题】{sub}\n【{tool_name}】{tool_arg}\n→ {result}")

        # 拼证据
        evidence = "\n\n".join(evidence_parts)

        # 反思：够不够？
        verdict = _reflect(query, evidence).strip()
        if verdict.upper().startswith("ENOUGH"):
            break
        # 不够 → 让模型再补子问题，进入下一轮
        more_text = verdict[4:].lstrip(":").strip() if verdict.upper().startswith("MORE") else verdict
        more = _parse_steps(more_text)
        if not more:
            break
        todo = more

    answer = _synthesize(query, evidence)
    return {"steps": raw, "evidence": evidence, "answer": answer, "rounds": rounds}
