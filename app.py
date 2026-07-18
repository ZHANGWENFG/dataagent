# -*- coding: utf-8 -*-
"""
app.py —— Streamlit 可视化界面（大白话版）
=======================================
把"智能问数 / 诊断分析 / 深度搜索"三个核心能力做成网页，简历演示一眼就懂。
设计要点：
  · 业务逻辑（run_query / run_diagnose / run_deep_search）抽成纯函数，方便离线单测；
  · 三个标签页共用一份会话记忆（st.session_state.mem），支持跨轮指代追问；
  · 只有 main() 里才调用 st.* 渲染界面，所以 `import app` 不会触发 Streamlit 运行时；
  · 没配 OPENAI_API_KEY 时，界面顶部弹黄条提示，但界面照常能打开（不会崩）。
运行：pip install streamlit && streamlit run app.py
"""

import os

import streamlit as st

from db import build
from sql_exec import run_sql
from nl2sql import nl2sql_self_correct
from diagnose import analyze
from memory import ConversationMemory
from cache import default_cache


# ---------------- 业务逻辑（纯函数，可离线测试）----------------
def run_query(question: str, memory: "ConversationMemory" = None) -> dict:
    """
    智能问数：生成 SQL → 在示例库执行（自带自检/反思重试）→ 返回结构化结果。
    传 memory 时，会用历史对话增强问题，支持"那北京呢？"这种指代追问。
    返回 {sql, result, error, retries, cache_hit}，上层直接展示。
    cache_hit=True 表示命中查询缓存，跳过了 LLM+SQL，直接返回上次结果。
    """
    build()  # 确保示例库存在
    # —— 查询缓存：同样的问题第二次直接命中，省一次 LLM + SQL ——
    hit = default_cache.get(question)
    if hit is not None:
        hit["cache_hit"] = True
        return hit
    q = memory.augment(question) if memory else question
    plan = nl2sql_self_correct(q, execute_fn=run_sql)
    result = {
        "sql": plan["sql"],
        "result": plan["result"],
        "error": plan["error"],
        "retries": plan["retries"],
        "cache_hit": False,
        "kb_context": plan.get("kb_context", ""),
    }
    default_cache.put(question, result)
    return result


def run_diagnose(question: str, memory: "ConversationMemory" = None,
                stream: bool = False) -> dict:
    """诊断分析：pandas 量化 + LLM 叙述，返回 {insights, conclusion, cache_hit}。
    stream=True 时 conclusion 是"流式生成器"，供界面逐字展示（流式结果不入缓存）。"""
    build()
    # 流式结果无法 JSON 缓存（是生成器），只在非流式时走缓存
    if not stream:
        hit = default_cache.get(question)
        if hit is not None:
            hit["cache_hit"] = True
            return hit
    q = memory.augment(question) if memory else question
    res = analyze(q, stream=stream)
    result = {"insights": res["insights"], "conclusion": res["conclusion"], "cache_hit": False}
    if not stream:
        default_cache.put(question, result)
    return result


def run_deep_search(question: str, memory: "ConversationMemory" = None,
                    stream: bool = False) -> dict:
    """
    深度搜索：顺序多步推理闭环（拆解→逐步检索证据→反思→综合）。
    返回 {steps, evidence, answer, rounds, cache_hit}：
      - steps   ：每一步"子问题→工具→证据"记录
      - answer  ：综合后的最终答案（stream=True 时为流式生成器）
    """
    build()
    if not stream:
        hit = default_cache.get(question)
        if hit is not None:
            hit["cache_hit"] = True
            return hit
    from deep_search import deep_search   # 懒加载，避免离线 import app 时连带触发重型依赖
    q = memory.augment(question) if memory else question
    result = deep_search(q, stream=stream)
    result["cache_hit"] = False
    if not stream:
        default_cache.put(question, result)
    return result


# ---------------- 界面（只在 streamlit run 时执行）----------------
def main():
    st.set_page_config(page_title="simple_data_agent 演示", layout="wide")
    st.title("📊 simple_data_agent · 纯 Python 智能问数 / 诊断演示")

    # 跨轮会话记忆：存在 st.session_state，三个标签页共用一份（像同一个聊天会话）
    if "mem" not in st.session_state:
        st.session_state.mem = ConversationMemory()
    # 没配 key 时给个醒目但不阻塞的提示
    if not os.getenv("OPENAI_API_KEY"):
        st.warning(
            "⚠️ 未检测到 OPENAI_API_KEY：界面可正常打开，但问数/诊断需要大模型才能出结果。"
            "运行前请先 `export OPENAI_API_KEY=xxx`。"
        )
    # 清空记忆按钮（新一轮调研用）
    if st.button("🧹 新对话", key="reset_mem"):
        st.session_state.mem.reset()
        st.success("已清空对话记忆，开启新一轮。")

    tab1, tab2, tab3 = st.tabs(["🔎 智能问数 (NL2SQL)", "🩺 诊断分析", "🧠 深度搜索 (DeepSearch)"])

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
                out = run_query(q, memory=st.session_state.mem)
            st.subheader("生成的 SQL")
            st.code(out["sql"], language="sql")
            if out["error"]:
                st.error(f"执行出错（重试 {out['retries']} 次）：{out['error']}")
            else:
                if out["cache_hit"]:
                    st.success("✅ 命中查询缓存，直接返回（省了一次 LLM + SQL）")
                elif out["retries"]:
                    st.info(f"SQL 曾跑挂，已自检重试 {out['retries']} 次后跑通 ✅")
                if out.get("kb_context"):
                    st.subheader("📚 命中业务口径（知识库 SOP）")
                    st.caption(out["kb_context"])
                st.subheader("查询结果")
                st.text(out["result"] or "（无数据）")
            # 记入会话记忆，供下一轮指代追问（如"那北京呢？"）
            st.session_state.mem.add("user", q)
            st.session_state.mem.add("assistant", out["result"] or out["error"] or "（无结果）")

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
                out = run_diagnose(d, memory=st.session_state.mem, stream=True)
            st.subheader("量化指标")
            st.write(out["insights"])
            st.subheader("业务结论（流式输出）")
            conclusion_text = st.write_stream(out["conclusion"])   # 逐字吐出，返回完整文本
            st.session_state.mem.add("user", d)
            st.session_state.mem.add("assistant", conclusion_text or "（无结论）")

    # 标签页 3：深度搜索（顺序多步推理闭环）
    with tab3:
        st.caption("问'深度/根因/综合'，系统会拆解子问题→逐步调工具拿证据→反思是否够→综合答案（区别于并行扇出）。")
        s = st.text_input(
            "你想深度调研什么",
            value="深度分析一下最近销售额下滑的根因是什么？",
            key="s_input",
        )
        if st.button("深度搜索", key="s_btn") and s.strip():
            with st.spinner("正在拆解并逐步检索证据…"):
                out = run_deep_search(s, memory=st.session_state.mem)
            st.subheader(f"检索过程（共 {len(out['steps'])} 步，{out['rounds']} 轮）")
            for i, step in enumerate(out["steps"], 1):
                st.markdown(f"**{i}. {step['sub']}**")
                st.caption(f"→ 调用工具 `{step['tool']}`，参数：{step['arg']}")
                st.text(step["result"])
            st.subheader("综合答案（流式输出）")
            answer_text = st.write_stream(out["answer"])   # 逐字吐出，返回完整文本
            st.session_state.mem.add("user", s)
            st.session_state.mem.add("assistant", answer_text or "（无答案）")


if __name__ == "__main__":
    main()
