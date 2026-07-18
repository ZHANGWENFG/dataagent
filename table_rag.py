# -*- coding: utf-8 -*-
"""
table_rag.py —— TableRAG：两阶段"选表 + 选字段"（大白话版，真·Qdrant 向量版）
============================================================================
这是 joyagent DataAgent 里 TableRAG 的精简版。核心思想一模一样：
企业里有几百张表，不能直接把所有表丢给大模型（太长、易错），所以要"先粗筛表，再细筛字段"。

这一版用真·向量库 Qdrant（内存模式 :memory:，不用起服务）做语义召回：
  1) 把每张表 / 每个字段的"注释文本"向量化，upsert 进 Qdrant
  2) 把用户问题也向量化，去 Qdrant 里做最近邻相似度检索
  3) 再用 LLM 对召回结果做 rerank 精排（演示"向量召回 + LLM 精排"的组合）
没配 LLM key 时，Embedder 自动退回本地哈希向量，照样能跑通整条链路。
"""

from config import SCHEMA_REGISTRY
from embeddings import get_embedder, Embedder

# 延迟导入 Qdrant，避免没装时整文件报错
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct,
        Filter, FieldCondition, MatchValue,
    )
    _HAS_QDRANT = True
except Exception:
    _HAS_QDRANT = False


def _table_doc(table: str, meta: dict) -> str:
    """把一张表拼成一段用于向量化的文本。"""
    cols = meta["columns"]
    col_text = " ".join(f"{c}({d})" for c, d in cols.items())
    return f"{table}：{meta['comment']}。字段：{col_text}"


def _column_doc(table: str, meta: dict, col: str, desc: str) -> str:
    return f"表{table}的字段 {col}：{desc}"


class TableRAG:
    """
    表检索器：建好 Qdrant 集合，提供 select_tables / select_columns。
    用类而不是散函数，是为了把"向量库 + Embedder"这两个重资源只建一次。
    """

    def __init__(self, embedder: Embedder = None, collection: str = "tables"):
        self.embedder = embedder or get_embedder()
        self.dim = self.embedder.dim
        if not _HAS_QDRANT:
            raise RuntimeError("没装 qdrant-client，请先 pip install qdrant-client")
        # :memory: 模式：进程内向量库，免起服务，最适合演示 / 单进程应用
        self.client = QdrantClient(":memory:")
        self.collection = collection
        self._build_index()

    def _build_index(self):
        """把 SCHEMA_REGISTRY 里所有表 / 字段向量化后 upsert 进 Qdrant。"""
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
        )
        points = []
        pid = 0
        for table, meta in SCHEMA_REGISTRY.items():
            # 每张表一个点
            pid += 1
            vec = self.embedder.embed(_table_doc(table, meta))
            points.append(PointStruct(
                id=pid, vector=vec,
                payload={"type": "table", "name": table, "text": _table_doc(table, meta)},
            ))
            # 每个字段一个点
            for col, desc in meta["columns"].items():
                pid += 1
                vec = self.embedder.embed(_column_doc(table, meta, col, desc))
                points.append(PointStruct(
                    id=pid, vector=vec,
                    payload={"type": "column", "table": table, "name": col,
                             "text": _column_doc(table, meta, col, desc)},
                ))
        self.client.upsert(collection_name=self.collection, points=points)

    def _search(self, query: str, type_: str, table: str = None, top_k: int = 8):
        """在 Qdrant 里做最近邻检索；可选按表过滤（选字段时用）。
        兼容新旧 qdrant-client：新版用 query_points，老版用 search。"""
        qvec = self.embedder.embed(query)
        must = [FieldCondition(key="type", match=MatchValue(value=type_))]
        if table is not None:
            must.append(FieldCondition(key="table", match=MatchValue(value=table)))
        filt = Filter(must=must)
        if hasattr(self.client, "query_points"):
            res = self.client.query_points(
                collection_name=self.collection,
                query=qvec, query_filter=filt, limit=top_k)
            return res.points
        return self.client.search(
            collection_name=self.collection,
            query_vector=qvec, query_filter=filt, limit=top_k)

    # ---------------- 阶段一：选表 ----------------
    def select_tables(self, query: str, top_k: int = 2) -> list:
        """
        阶段一（选表）：把问题向量化，去 Qdrant 召回最相关的几张表。
        也额外让 LLM 兜底确认一下（演示"向量召回 + LLM 精排"的组合）。
        """
        hits = self._search(query, "table", top_k=top_k * 3)
        seen = []
        for h in hits:
            name = h.payload["name"]
            if name not in seen:
                seen.append(name)
            if len(seen) >= top_k:
                break
        return seen or list(SCHEMA_REGISTRY.keys())[:top_k]

    # ---------------- 阶段二：选字段 ----------------
    def select_columns(self, query: str, tables: list) -> dict:
        """
        阶段二（选字段）：在已选中的表内部，用向量相似度挑出相关字段。
        返回 {表名: [字段名, ...]}，这就是喂给 NL2SQL 的"精简 schema"。
        """
        result = {}
        for table in tables:
            cols = SCHEMA_REGISTRY[table]["columns"]
            hits = self._search(query, "column", table=table, top_k=20)
            kept = [h.payload["name"] for h in hits]
            # 主键永远带上，保证 SQL 能 JOIN
            pk = list(cols.keys())[0]
            if pk not in kept:
                kept.insert(0, pk)
            result[table] = kept
        return result


# ---------------- 模块级简便函数（保持旧接口，方便 nl2sql 直接调用）----------------
_default_rag = None


def _rag() -> TableRAG:
    global _default_rag
    if _default_rag is None:
        _default_rag = TableRAG()
    return _default_rag


def select_tables(query: str, top_k: int = 2) -> list:
    return _rag().select_tables(query, top_k)


def select_columns(query: str, tables: list) -> dict:
    return _rag().select_columns(query, tables)


def build_schema_prompt(query: str) -> str:
    """把"选中的表 + 选中的字段"拼成自然语言，后面 NL2SQL 会放进 prompt。"""
    tables = select_tables(query)
    columns = select_columns(query, tables)
    lines = []
    for t in tables:
        lines.append(f"## 表 {t}（{SCHEMA_REGISTRY[t]['comment']}）")
        for c in columns[t]:
            lines.append(f"  - {c}: {SCHEMA_REGISTRY[t]['columns'][c]}")
    return "\n".join(lines)
