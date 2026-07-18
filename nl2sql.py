# -*- coding: utf-8 -*-
"""
nl2sql.py —— 自然语言转 SQL（大白话版）
=======================================
对标 joyagent 的 NL2SQLAgent：分三段，和源码里的 rewrite→think→convert 一一对应。
  rewrite ：把口语化问题润色清晰（"上月卖得最好的"→明确时间窗口和指标）
  think   ：基于 TableRAG 给的 schema 先推理"该查哪些表、怎么聚合"
  convert ：综合前两步，低温度生成稳定 SQL
"""

from llm import ask
from table_rag import build_schema_prompt


def rewrite(query: str) -> str:
    """第一段：改写。让模型把模糊说法改成精确表达。"""
    sys = "你是 SQL 语义专家。把用户的口语问题改写成清晰、无歧义的数据查询描述，不要写 SQL。"
    return ask(f"原始问题：{query}\n请改写：", system=sys, temperature=0.3)


def think(query: str, rewritten: str, schema_text: str) -> str:
    """第二段：思考（流式思维链）。让模型先讲清楚'打算怎么查'。"""
    sys = "你是数据分析师。基于下面的表结构，说出求解思路（查哪张表、按什么分组/过滤、用什么聚合），不要写最终 SQL。"
    prompt = f"问题：{query}\n改写后：{rewritten}\n可用表结构：\n{schema_text}\n请说明分析思路："
    return ask(prompt, system=sys, temperature=0.0)


def convert(query: str, rewritten: str, thinking: str, schema_text: str, dialect: str = "sqlite") -> str:
    """第三段：生成 SQL。低温度保证稳定。返回纯 SQL 文本。"""
    sys = f"你是 {dialect} SQL 专家。只输出一条可执行的 SQL，不要解释、不要 markdown 代码块标记。"
    prompt = (
        f"问题：{query}\n改写：{rewritten}\n思路：{thinking}\n"
        f"可用表结构：\n{schema_text}\n请生成 SQL："
    )
    sql = ask(prompt, system=sys, temperature=0.0)
    return sql.strip().strip("`").replace("```sql", "").replace("```", "").strip()


def nl2sql(query: str) -> dict:
    """
    对外总入口：跑完三段，返回结构化结果。
    上层（工具 / Agent）拿到 SQL 后，丢给 SQLExecuteTool 在真实库上执行。
    """
    schema_text = build_schema_prompt(query)   # TableRAG 先选出相关表字段
    rewritten = rewrite(query)
    thinking = think(query, rewritten, schema_text)
    sql = convert(query, rewritten, thinking, schema_text)
    return {"rewritten": rewritten, "thinking": thinking, "sql": sql}
