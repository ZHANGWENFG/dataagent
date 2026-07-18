# -*- coding: utf-8 -*-
"""
table_rag.py —— TableRAG：两阶段"选表 + 选字段"（大白话版，混合召回版）
============================================================================
这是 joyagent DataAgent 里 TableRAG 的精简版。核心思想一模一样：
企业里有几百张表，不能直接把所有表丢给大模型（太长、易错），所以要"先粗筛表，再细筛字段"。

这一版走"混合召回（hybrid retrieval）"，对标 joyagent 的 Qdrant(向量) + ES(关键词) 双路：
  · 向量路径：用真·向量库 Qdrant（内存模式 :memory:）做语义相似度召回
  · 关键词路径：用纯 Python 实现的 BM25 做精确词面匹配召回（不依赖外部 ES）
  · 融合：用 RRF（Reciprocal Rank Fusion，倒数排名融合）把两路结果合成一份排序
  没配 LLM key 时，Embedder 自动退回本地哈希向量，照样能跑通整条链路。
（再下一步会在融合结果上叠加一层 LLM rerank 精排，见 Task5。）
"""

import math
import re

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


def _tokenize(text: str) -> list:
    """极简分词：英文按空白切、中文按单字切（演示够用，不引第三方分词库）。"""
    tokens = []
    for w in text.lower().split():
        tokens.append(w)
    for ch in text:
        if "\u4e00" <= ch <= "\u9fa5":
            tokens.append(ch)
    return tokens


class BM25:
    """
    纯 Python 实现的 BM25（关键词召回路径，对标 joyagent 的 ES 关键词检索）。
    为什么需要它：向量召回擅长"意思相近"，但不擅长"精确词面命中"
    （比如用户直接敲了字段名 order_id、amount）。BM25 正好补这个短板。
    它不依赖任何外部服务，纯算数，离线即可跑。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1   # 词频饱和系数：词出现越多越相关，但收益递减
        self.b = b     # 文档长度归一化：长文档天然词多，要打压一下
        self.docs = []          # 原始 token 列表
        self.doc_lens = []      # 每个文档长度
        self.avgdl = 0.0        # 平均文档长度
        self.df = {}            # term -> 出现它的文档数（document frequency）
        self.idf = {}           # term -> 逆文档频率（越稀有越值钱）
        self.doc_count = 0

    def add_documents(self, docs: list):
        """把一批文档灌进来，算好 idf 等静态量。"""
        self.docs = [_tokenize(d) for d in docs]
        self.doc_count = len(self.docs)
        self.doc_lens = [len(d) for d in self.docs]
        self.avgdl = sum(self.doc_lens) / self.doc_count if self.doc_count else 0
        self.df = {}
        for d in self.docs:
            for t in set(d):               # set 去重：一个词在一篇文档里只计一次 df
                self.df[t] = self.df.get(t, 0) + 1
        for t, n in self.df.items():
            # 标准 idf 公式（加 1 平滑，避免负无穷）
            self.idf[t] = math.log((self.doc_count - n + 0.5) / (n + 0.5) + 1.0)

    def search(self, query: str, top_k: int = None) -> list:
        """返回 [(文档下标, 分数), ...]，按分数从高到低。"""
        q_tokens = _tokenize(query)
        scores = []
        for i, doc in enumerate(self.docs):
            score = self._score(q_tokens, doc, self.doc_lens[i])
            scores.append((i, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        if top_k:
            scores = scores[:top_k]
        return scores

    def _score(self, q_tokens: list, doc: list, doc_len: int) -> float:
        tf_map = {}
        for t in doc:
            tf_map[t] = tf_map.get(t, 0) + 1
        score = 0.0
        for qt in q_tokens:
            if qt not in tf_map:
                continue
            idf = self.idf.get(qt, 0.0)
            tf = tf_map[qt]
            # BM25 单词语义分数 = idf * (tf*(k1+1)) / (tf + k1*(1 - b + b*dl/avgdl))
            denom = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1))
            score += idf * (tf * (self.k1 + 1)) / denom
        return score


def _rrf(ranked_lists: list, k: int = 60) -> dict:
    """
    RRF（Reciprocal Rank Fusion，倒数排名融合）：把多路有序召回合成一份排序。
    这是工业界混合检索的标配做法（joyagent 的向量+ES 双路也用类似融合）。
    :param ranked_lists: [[id_a, id_b, ...], [id_x, id_y, ...], ...] 每个子列表从相关到不相关
    :param k: 平滑常数（默认 60，经验值），防止排名靠前的项分数碾压一切
    :return: {候选id: 融合分数}，分数越高越该排前面
    直觉：一个候选在两路都排第 1，比只在一路排第 1 更可信；RRF 用 1/(k+rank) 累加表达这个"双重确认"。
    """
    fused = {}
    for rl in ranked_lists:
        for rank, cid in enumerate(rl, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
    return fused


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

        # ---- 关键词路径：纯 Python BM25 索引（对标 joyagent 的 ES 关键词检索）----
        # 向量路径擅长"语义相近"，BM25 擅长"词面精确命中"，两条路互补。
        self.table_bm25 = BM25()
        self._table_by_index = {}      # BM25 文档下标 -> 表名
        table_docs = []
        for table, meta in SCHEMA_REGISTRY.items():
            self._table_by_index[len(table_docs)] = table
            table_docs.append(_table_doc(table, meta))
        self.table_bm25.add_documents(table_docs)

        self.column_bm25 = BM25()
        self._col_by_index = {}        # BM25 文档下标 -> (表名, 字段名)
        col_docs = []
        for table, meta in SCHEMA_REGISTRY.items():
            for col, desc in meta["columns"].items():
                self._col_by_index[len(col_docs)] = (table, col)
                col_docs.append(_column_doc(table, meta, col, desc))
        self.column_bm25.add_documents(col_docs)

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
        阶段一（选表）：混合召回 = 向量路径(Qdrant) + 关键词路径(BM25)，再用 RRF 融合。
        例：用户问"销售额最高的城市"——
          向量路径靠"销售额/城市"语义把 sales_order 召回；
          BM25 靠词面命中 amount(金额)/city(城市) 再次确认；
          两路都认它，融合分最高，自然排第一。
        """
        # 向量路径：Qdrant 最近邻，拿到一个按相关度排好的表名列表
        vec_hits = self._search(query, "table", top_k=len(SCHEMA_REGISTRY))
        vec_rank = [h.payload["name"] for h in vec_hits]
        # 关键词路径：BM25，拿到另一个按 BM25 分数排好的表名列表
        bm25_res = self.table_bm25.search(query, top_k=None)
        bm25_rank = [self._table_by_index[i] for i, _ in bm25_res]
        # 两路融合：RRF 把"两路都靠前"的表顶上来
        fused = _rrf([vec_rank, bm25_rank])
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
        selected = [name for name, _ in ranked[:top_k]]
        return selected or list(SCHEMA_REGISTRY.keys())[:top_k]

    # ---------------- 阶段二：选字段 ----------------
    def select_columns(self, query: str, tables: list) -> dict:
        """
        阶段二（选字段）：在每张已选中的表内部，同样用"向量 + BM25 + RRF"挑相关字段。
        返回 {表名: [字段名, ...]}，这就是喂给 NL2SQL 的"精简 schema"。
        """
        result = {}
        for table in tables:
            cols = SCHEMA_REGISTRY[table]["columns"]
            # 向量路径：只在这一张表里找字段
            vec_hits = self._search(query, "column", table=table, top_k=20)
            vec_rank = [h.payload["name"] for h in vec_hits]
            # 关键词路径：BM25 全量检索后，只保留属于这张表的字段
            bm25_res = self.column_bm25.search(query, top_k=None)
            bm25_rank = [self._col_by_index[i][1] for i, _ in bm25_res
                         if self._col_by_index[i][0] == table]
            fused = _rrf([vec_rank, bm25_rank])
            ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)
            kept = [col for col, _ in ranked]
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
