# -*- coding: utf-8 -*-
"""
kb.py —— 业务知识库问答（SOP 召回，大白话版）
============================================
对标 joyagent 的 plan_sop.py（SOP / 业务口径召回）：用户问"销售额"时，
不同人理解不同（含不含退款？按下单日还是付款日？）。
我们在问数 / 诊断前，先从一份业务知识库（knowledge/*.md）里召回最相关的
"口径 / 定义"SOP，注入到 LLM 提示里，让生成结果对齐正确口径，避免歧义。
检索用 BM25(关键词) + LocalHashEmbedder(向量) 双路 + RRF 融合，离线零依赖。
"""

import os
import glob
from table_rag import BM25, _rrf
from embeddings import LocalHashEmbedder


def load_knowledge(dir_path: str = None) -> list:
    """
    加载 knowledge/ 下所有 md，按 "## " 切成"块"（每块是业务口径的一个小主题）。
    返回 [(块标题, 块文本), ...]。
    """
    if dir_path is None:
        dir_path = os.path.join(os.path.dirname(__file__), "knowledge")
    chunks = []
    for path in sorted(glob.glob(os.path.join(dir_path, "*.md"))):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        # 按二级标题 "## " 切分（第一篇可能以 "# 标题" 开头，没有 "## "）
        parts = text.split("\n## ")
        for i, part in enumerate(parts):
            if not part.strip():
                continue
            if i == 0:
                title = part.splitlines()[0].lstrip("# ").strip() or "总览"
                body = part.strip()
            else:
                title = part.splitlines()[0].strip()
                body = ("## " + part).strip()
            chunks.append((title, body))
    return chunks


class KnowledgeBase:
    """轻量知识库：双路召回（BM25 + 向量）后 RRF 融合，返回最相关的口径块。"""

    def __init__(self, dir_path: str = None, top_k: int = 3):
        self.chunks = load_knowledge(dir_path)
        self.texts = [c[1] for c in self.chunks]
        self.top_k = top_k
        # 双路索引：关键词路径 + 向量路径
        self.bm25 = BM25()
        self.bm25.add_documents(self.texts)
        self.embedder = LocalHashEmbedder()
        self.vectors = [self.embedder.embed(t) for t in self.texts]

    def _vector_search(self, query: str, top_k: int = None) -> list:
        qv = self.embedder.embed(query)
        scored = []
        for i, v in enumerate(self.vectors):
            dot = sum(a * b for a, b in zip(qv, v))   # 向量已 L2 归一化 → 点积即余弦
            scored.append((i, dot))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k] if top_k else scored

    def retrieve(self, query: str, top_k: int = None) -> list:
        """返回最相关的 top_k 个 (标题, 文本) 块。"""
        tk = top_k or self.top_k
        bm25_hits = self.bm25.search(query, top_k=len(self.texts))
        vec_hits = self._vector_search(query, top_k=len(self.texts))
        # _rrf 吃"候选 id 列表"，而 search 返回的是 (id, 分数) 元组，先取 id
        fused = _rrf([[i for i, _ in bm25_hits], [i for i, _ in vec_hits]])
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:tk]
        return [(self.chunks[i][0], self.chunks[i][1]) for i, _ in ranked]  # i 即块下标

    def context_text(self, query: str, top_k: int = None) -> str:
        """把召回的块拼成一段"业务口径参考"文本，直接塞进 LLM 提示。"""
        hits = self.retrieve(query, top_k)
        if not hits:
            return ""
        lines = ["【业务口径参考（来自知识库 SOP）】"]
        for title, body in hits:
            lines.append(f"- （{title}）{body}")
        return "\n".join(lines)


# 默认知识库（懒加载：第一次用才建索引，避免 import 时白白算向量）
_default_kb = None


def get_kb() -> KnowledgeBase:
    global _default_kb
    if _default_kb is None:
        _default_kb = KnowledgeBase()
    return _default_kb
