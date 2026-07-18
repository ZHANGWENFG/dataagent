# -*- coding: utf-8 -*-
"""
nl2sql.py —— 自然语言转 SQL（大白话版）
=======================================
对标 joyagent 的 NL2SQLAgent：分三段，和源码里的 rewrite→think→convert 一一对应。
  rewrite ：把口语化问题润色清晰（"上月卖得最好的"→明确时间窗口和指标）
  think   ：基于 TableRAG 给的 schema 先推理"该查哪些表、怎么聚合"
  convert ：综合前两步，低温度生成稳定 SQL
此外再叠加一层 **自检/反思循环（self-correction）**：生成 SQL 后真的去库上跑，
报错或空结果就把"报错信息"回喂给 LLM 让它改 SQL 再试，直到跑通或重试耗尽。
这正是对标 joyagent 里 NL2SQLAgent 的 self-correction 能力——真实项目里 SQL
一次写对的概率不高，会"改自己写的 SQL"才是能用的系统。
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
    （想要"生成即自检"的版本，请用 nl2sql_self_correct）
    """
    schema_text = build_schema_prompt(query)   # TableRAG 先选出相关表字段
    rewritten = rewrite(query)
    thinking = think(query, rewritten, schema_text)
    sql = convert(query, rewritten, thinking, schema_text)
    return {"rewritten": rewritten, "thinking": thinking, "sql": sql}


def _fix_sql(query: str, schema_text: str, bad_sql: str, error: str,
             dialect: str = "sqlite") -> str:
    """
    自检循环的"修正"步：把跑挂的 SQL + 报错信息 回喂给 LLM，让它改出一条新的。
    """
    sys = (f"你是 {dialect} SQL 专家。下面这条 SQL 执行出错，请修正后"
           f"只输出一条可执行 SQL，不要解释、不要 markdown 代码块。")
    prompt = (
        f"问题：{query}\n可用表结构：\n{schema_text}\n"
        f"出错的 SQL：\n{bad_sql}\n错误信息：{error}\n请输出修正后的 SQL："
    )
    sql = ask(prompt, system=sys, temperature=0.0)
    return sql.strip().strip("`").replace("```sql", "").replace("```", "").strip()


def nl2sql_self_correct(query: str, execute_fn=None, max_retries: int = 2,
                        dialect: str = "sqlite") -> dict:
    """
    带"自检/反思循环"的 NL2SQL 总入口（对标 joyagent 的 self-correction）。
    流程：
      1) 先走 rewrite→think→convert 三段生成 SQL
      2) 如果传入了 execute_fn（执行函数，约定：成功返回结果字符串，失败抛异常），就真去跑
      3) 跑挂了 → 把报错回喂 _fix_sql 让 LLM 改 SQL → 再跑，最多重试 max_retries 次
      4) 没配 LLM key 时改不了 SQL，就不再重试，直接把错误交出去（离线零依赖不崩）
    返回：{rewritten, thinking, sql, executed, result, error, retries}
      - sql      ：最终（可能已被修正过的）SQL
      - result   ：execute_fn 成功时的结果文本；失败/未执行则为 None
      - error    ：最后一次错误信息；成功则为 None
      - retries  ：为跑通而重试的次数
    """
    from config import LLM_API_KEY
    can_fix = bool(LLM_API_KEY)          # 没 key 就没法让 LLM 改 SQL，跳过重试

    schema_text = build_schema_prompt(query)
    rewritten = rewrite(query)
    thinking = think(query, rewritten, schema_text)
    sql = convert(query, rewritten, thinking, schema_text, dialect)

    result, error, retries = None, None, 0
    if execute_fn is None:
        return {"rewritten": rewritten, "thinking": thinking, "sql": sql,
                "executed": False, "result": None, "error": None, "retries": 0}

    try:
        result = execute_fn(sql)         # 第一次执行
    except Exception as e:
        error = str(e)
        if not can_fix:                  # 没 key，改不了，直接认栽
            return {"rewritten": rewritten, "thinking": thinking, "sql": sql,
                    "executed": True, "result": None, "error": error, "retries": 0}
        # 有 key：进入"报错→修正→再试"循环
        for _ in range(max_retries):
            retries += 1
            try:
                sql = _fix_sql(query, schema_text, sql, error, dialect)
                result = execute_fn(sql)
                error = None
                break
            except Exception as e2:
                error = str(e2)          # 记下最新的错，下一轮接着喂给 LLM
    return {"rewritten": rewritten, "thinking": thinking, "sql": sql,
            "executed": True, "result": result, "error": error, "retries": retries}
