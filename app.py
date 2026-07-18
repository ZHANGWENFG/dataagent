# -*- coding: utf-8 -*-
"""
app.py —— Streamlit 可视化界面（大白话版）
=======================================
把"智能问数"和"诊断分析"两个核心能力做成网页，简历演示一眼就懂。
设计要点：
  · 业务逻辑（run_query / run_diagnose）抽成纯函数，方便离线单测，不放进 UI 里；
  · 只有 main() 里才调用 st.* 渲染界面，所以 `import app` 不会触发 Streamlit 运行时，
    离线冒烟测试直接调 run_query/run_diagnose 即可；
  · 没配 OPENAI_API_KEY 时，界面顶部弹黄条提示，但界面照常能打开（不会崩）。
运行：pip install streamlit && streamlit run app.py
"""

import os

import streamlit as st

from db import build
from sql_exec import run_sql
from nl2sql import nl2sql_self_correct
from diagnose import analyze


# ---------------- 业务逻辑（纯函数，可离线测试）----------------
def run_query(question: str) -> dict:
    """
    智能问数：生成 SQL → 在示例库执行（自带自检/反思重试）→ 返回结构化结果。
    返回 {sql, result, error, retries}，上层直接展示。
    """
    build()  # 确保示例库存在
    plan = nl2sql_self_correct(question, execute_fn=run_sql)
    return {
        "sql": plan["sql"],
        "result": plan["result"],
        "error": plan["error"],
        "retries": plan["retries"],
    }


def run_diagnose(question: str) -> dict:
    """诊断分析：pandas 量化 + LLM 叙述，返回 {insights, conclusion}。"""
    build()
    res = analyze(question)
    return {"insights": res["insights"], "conclusion": res["conclusion"]}


# ---------------- 界面（只在 streamlit run 时执行）----------------
def main():
    st.set_page_config(page_title="simple_data_agent 演示", layout="wide")
    st.title("📊 simple_data_agent · 纯 Python 智能问数 / 诊断演示")

    # 没配 key 时给个醒目但不阻塞的提示
    if not os.getenv("OPENAI_API_KEY"):
        st.warning(
            "⚠️ 未检测到 OPENAI_API_KEY：界面可正常打开，但问数/诊断需要大模型才能出结果。"
            "运行前请先 `export OPENAI_API_KEY=xxx`。"
        )

    tab1, tab2 = st.tabs(["🔎 智能问数 (NL2SQL)", "🩺 诊断分析"])

    # 标签页 1：自然语言问数
    with tab1:
        st.caption("用大白话提问，系统自动选表选字段、生成 SQL 并执行（跑挂会自动改 SQL 重试）。")
        q = st.text_input(
            "你的问题",
            value="各城市销售额总和是多少？哪个城市最高？",
            key="q_input",
        )
        if st.button("查询", key="q_btn") and q.strip():
            with st.spinner("正在生成 SQL 并执行…"):
                out = run_query(q)
            st.subheader("生成的 SQL")
            st.code(out["sql"], language="sql")
            if out["error"]:
                st.error(f"执行出错（重试 {out['retries']} 次）：{out['error']}")
            else:
                if out["retries"]:
                    st.info(f"SQL 曾跑挂，已自检重试 {out['retries']} 次后跑通 ✅")
                st.subheader("查询结果")
                st.text(out["result"] or "（无数据）")

    # 标签页 2：诊断分析
    with tab2:
        st.caption("问'为什么/分析一下'，系统做趋势/异常/周期/相关性量化并用人话解释。")
        d = st.text_input(
            "你想诊断什么",
            value="分析一下最近销售额的变化趋势和异常",
            key="d_input",
        )
        if st.button("诊断", key="d_btn") and d.strip():
            with st.spinner("正在量化分析…"):
                out = run_diagnose(d)
            st.subheader("量化指标")
            st.write(out["insights"])
            st.subheader("业务结论")
            st.write(out["conclusion"])


if __name__ == "__main__":
    main()
