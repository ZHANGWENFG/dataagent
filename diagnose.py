# -*- coding: utf-8 -*-
"""
diagnose.py —— 诊断分析 / 归因（大白话版）
=========================================
对标 joyagent 的 auto_analysis：不是让模型"凭空编结论"，
而是先用量化方法（pandas）算出趋势/周期/异常/相关性，再让 LLM 把数字讲成人话。
这才是靠谱的"诊断"，而不是瞎猜。
"""

import sqlite3
import pandas as pd
from db import DB_PATH
from llm import ask
from kb import get_kb


def _load_monthly_sales() -> pd.DataFrame:
    """从示例库读销售数据，按"月份"汇总成销售额序列。"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT order_date, amount FROM sales_order", conn)
    conn.close()
    df["month"] = df["order_date"].str[:7]          # 取 YYYY-MM 当月份
    monthly = df.groupby("month")["amount"].sum().reset_index()
    monthly["amount"] = monthly["amount"].astype(float)
    return monthly


def analyze(query: str) -> dict:
    """
    执行诊断分析，返回结构化洞察 + LLM 叙述。
    这里演示四种最常见的归因方法（和 joyagent 的 InsightTool 思路一致）。
    """
    monthly = _load_monthly_sales()
    vals = monthly["amount"].tolist()

    insights = {}

    # 1) 趋势：用首尾两个月对比 + 线性回归斜率方向
    insights["趋势"] = {
        "首月": round(vals[0], 1),
        "末月": round(vals[-1], 1),
        "变化率": f"{round((vals[-1]-vals[0])/vals[0]*100, 1)}%",
    }

    # 2) 异常：用"均值 ± 2倍标准差"找出离群月份（我们埋的第90天暴跌会被抓到）
    mean, std = pd.Series(vals).mean(), pd.Series(vals).std()
    anomalies = [m for m, v in zip(monthly["month"], vals) if abs(v - mean) > 2 * std]
    insights["异常月份"] = anomalies or "无明显异常"

    # 3) 周期：看月度环比（相邻月变化），判断有没有规律波动
    mom = [round((vals[i] - vals[i-1]) / vals[i-1] * 100, 1) for i in range(1, len(vals))]
    insights["环比波动"] = mom

    # 4) 相关性：销售额 vs 订单量（这里用数量近似，演示 corr 方法）
    conn = sqlite3.connect(DB_PATH)
    qty = pd.read_sql_query(
        "SELECT order_date, quantity FROM sales_order", conn)
    conn.close()
    qty["month"] = qty["order_date"].str[:7]
    qty_m = qty.groupby("month")["quantity"].sum().reset_index()
    merged = monthly.merge(qty_m, on="month")
    corr = merged["amount"].corr(merged["quantity"])
    insights["销售额与销量相关性"] = round(float(corr), 3)

    # 最后让 LLM 把上面的数字讲成"人话结论"（先召回业务口径 SOP 注入，避免口径歧义）
    kb_context = get_kb().context_text(query)
    narrative = ask(
        f"用户问题：{query}\n以下是自动算出的量化指标：\n{insights}\n"
        f"{kb_context}\n"
        f"请给出一段业务诊断结论，指出最值得关注的异常和原因假设。",
        system="你是资深业务分析师，结论要具体、可行动。", temperature=0.4)

    return {"insights": insights, "conclusion": narrative, "kb_context": kb_context}
