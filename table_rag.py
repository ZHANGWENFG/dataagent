# -*- coding: utf-8 -*-
"""
table_rag.py —— TableRAG：两阶段"选表 + 选字段"（大白话版）
=========================================================
这是 joyagent DataAgent 里 TableRAG 的精简版。核心思想一模一样：
企业里有几百张表，问一个问题，不能直接把所有表都丢给大模型（太长、易错），
所以要"先粗筛表，再细筛字段"。

我们这里没接 Qdrant/ES 向量库，用"关键词重合度打分"代替向量相似度，
这样零依赖就能跑；你以后想换真向量库，只要改 score_table / score_column 这两个函数即可。
"""

import re
from config import SCHEMA_REGISTRY
from llm import ask_json

# 中文分词：没有 jieba 也能跑的极简版（按字+常见词切），够演示用
_STOP = set("的吗了和是在与我他它这那有及为被把被将已吗呢吧啊")


def tokenize(text: str):
    """把一句话拆成关键词集合（去标点、去虚词）。"""
    text = re.sub(r"[^\w\u4e00-\u9fa5]", " ", text)   # 去掉标点
    # 英文按词、中文按字（演示用，真实项目用 jieba 更准）
    toks = []
    for w in text.split():
        toks.append(w.lower())
    for ch in text:
        if "\u4e00" <= ch <= "\u9fa5" and ch not in _STOP:
            toks.append(ch)
    return set(toks)


def _score(query_tokens: set, text: str) -> float:
    """关键词重合度打分：query 里的词，在表/字段描述里出现了几个。"""
    doc_tokens = tokenize(text)
    if not doc_tokens:
        return 0.0
    hit = query_tokens & doc_tokens
    return len(hit) / len(query_tokens)   # 命中比例越高分越高


# ---------------- 阶段一：选表 ----------------
def select_tables(query: str, top_k: int = 2) -> list:
    """
    阶段一（选表）：给每个表算分，取分数最高的 top_k 张表。
    也额外让 LLM 兜底确认一下（演示"向量召回 + LLM 精排"的组合）。
    """
    q_tokens = tokenize(query)
    scored = []
    for table, meta in SCHEMA_REGISTRY.items():
        # 表注释 + 所有字段名/注释 拼成一段文本来打分
        doc = meta["comment"] + " " + " ".join(meta["columns"].keys()) + " " + " ".join(meta["columns"].values())
        scored.append((table, _score(q_tokens, doc)))
    scored.sort(key=lambda x: x[1], reverse=True)
    chosen = [t for t, s in scored[:top_k] if s > 0]
    return chosen or [scored[0][0]]   # 兜底：至少返回分数最高的那张


# ---------------- 阶段二：选字段 ----------------
def select_columns(query: str, tables: list) -> dict:
    """
    阶段二（选字段）：在已选中的表内部，再挑出和问题相关的字段。
    返回 {表名: [字段名, ...]}，这就是喂给 NL2SQL 的"精简 schema"。
    """
    q_tokens = tokenize(query)
    result = {}
    for table in tables:
        cols = SCHEMA_REGISTRY[table]["columns"]
        kept = []
        for col, desc in cols.items():
            # 字段名或字段注释里命中了 query 关键词，就保留
            if _score(q_tokens, f"{col} {desc}") > 0:
                kept.append(col)
        # 主键永远带上，保证 SQL 能 JOIN
        pk = list(cols.keys())[0]
        if pk not in kept:
            kept.insert(0, pk)
        result[table] = kept
    return result


# ---------------- 组装成"给 NL2SQL 看的 schema 文本" ----------------
def build_schema_prompt(query: str) -> str:
    """
    把"选中的表 + 选中的字段"拼成一段自然语言描述，
    后面 NL2SQL 会把它放进 prompt，告诉模型"只能用这些表和字段"。
    """
    tables = select_tables(query)
    columns = select_columns(query, tables)
    lines = []
    for t in tables:
        lines.append(f"## 表 {t}（{SCHEMA_REGISTRY[t]['comment']}）")
        for c in columns[t]:
            lines.append(f"  - {c}: {SCHEMA_REGISTRY[t]['columns'][c]}")
    return "\n".join(lines)
