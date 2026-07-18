# -*- coding: utf-8 -*-
"""
eval.py —— 离线评测集（大白话版）
================================
固定一批问数问题，离线（不依赖 LLM key）量化两件事：
  1) 选表准确率：TableRAG 有没有把"该查的表"选出来（混合召回质量的硬指标）
  2) SQL 可执行率：选表 → 生成 SQL → 在 demo.db 跑，整条链路能不能跑通
默认走"模板 SQL"（按选中的表生成能跑的聚合查询，非 LLM 生成，仅验证链路）；
若设置了 OPENAI_API_KEY，则自动切换成真实 NL2SQL（跑的是模型写的 SQL），可执行率更硬核。
CI 里就跑这个脚本，零密钥也能给出选表准确率。

运行：python eval.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import LLM_API_KEY
from db import build
from table_rag import select_tables
from sql_exec import run_sql

# 固定评测问题：问题 -> 期望出现在 top_k 候选里的表（任中一个即算对）
CASES = [
    ("统计各个城市的销售总额",            ["sales_order"]),
    ("销量最高的商品类目有哪些",          ["product", "sales_order"]),
    ("会员等级的分布情况",                ["user"]),
    ("订单金额大于 100 的城市",           ["sales_order"]),
    ("哪个品牌卖得最好",                  ["product", "sales_order"]),
    ("不同渠道的下单量对比",              ["sales_order"]),
    ("各城市的用户数量",                  ["user"]),
]


def _template_sql(tables: list) -> str:
    """离线用的"模板 SQL"：按选中的表生成一个能在 demo.db 跑的聚合查询（非 LLM 生成）。"""
    if "sales_order" in tables:
        return "SELECT city, SUM(amount) AS total FROM sales_order GROUP BY city ORDER BY total DESC LIMIT 5"
    if "product" in tables:
        return "SELECT category, COUNT(*) AS cnt FROM product GROUP BY category"
    if "user" in tables:
        return "SELECT vip_level, COUNT(*) AS cnt FROM user GROUP BY vip_level"
    return "SELECT 1"


def evaluate(top_k: int = 2) -> bool:
    """跑完整评测，打印选表准确率 / SQL 可执行率，全部通过返回 True。"""
    build()  # 确保示例库存在
    use_real_llm = bool(LLM_API_KEY)

    sel_ok = exec_ok = 0
    for q, expect in CASES:
        tabs = select_tables(q, top_k=top_k)
        hit = any(e in tabs for e in expect)
        sel_ok += 1 if hit else 0

        # 生成 SQL：有 key 用真实 NL2SQL（带自检），没 key 用模板 SQL
        if use_real_llm:
            from nl2sql import nl2sql_self_correct
            sql = nl2sql_self_correct(q, execute_fn=run_sql)["sql"]
        else:
            sql = _template_sql(tabs)

        try:
            run_sql(sql)
            exec_ok += 1
        except Exception as e:
            print(f"  ✗ SQL 执行失败 [{q}] -> {sql}\n     {e}")

    total = len(CASES)
    sel_rate = sel_ok / total * 100
    exec_rate = exec_ok / total * 100
    mode = "真实 NL2SQL" if use_real_llm else "模板 SQL(离线)"
    print(f"评测模式：{mode}")
    print(f"选表准确率 : {sel_ok}/{total} = {sel_rate:.0f}%")
    print(f"SQL可执行率: {exec_ok}/{total} = {exec_rate:.0f}%")
    return sel_ok == total and exec_ok == total


if __name__ == "__main__":
    ok = evaluate()
    sys.exit(0 if ok else 1)
