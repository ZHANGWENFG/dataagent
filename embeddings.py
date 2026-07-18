# -*- coding: utf-8 -*-
"""
embeddings.py —— 文本向量化（大白话版）
=====================================
TableRAG 要"按语义找最相关的表/字段"，本质是做向量相似度检索。
这里提供两种 Embedder，都实现同一个 embed(text) -> list[float] 接口：
  - OpenAIEmbedder  ：调用 OpenAI 兼容接口生成"真·语义向量"（需要 LLM_API_KEY）
  - LocalHashEmbedder：离线兜底，用"关键词哈希"生成固定维度向量（不需要网络）
table_rag 不关心用的是哪种，只要能拿到向量去 Qdrant 里比相似度就行。
"""

import hashlib
import math
from abc import ABC, abstractmethod

try:
    from openai import OpenAI
    from config import LLM_BASE_URL, LLM_API_KEY
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False


class Embedder(ABC):
    """所有向量化器的父类：只要能返回一段浮点向量即可。"""
    dim: int = 0

    @abstractmethod
    def embed(self, text: str) -> list:
        ...


class OpenAIEmbedder(Embedder):
    """真·语义向量：调用 embeddings 接口（默认和对话同一个 LLM 厂商）。"""

    def __init__(self, model: str = "text-embedding-3-small"):
        if not _HAS_OPENAI or not LLM_API_KEY:
            raise RuntimeError("OpenAIEmbedder 需要 OPENAI_API_KEY（或配置好的 LLM 环境变量）")
        self.model = model
        self._client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        # 先用一条文本探一下维度，后面 upsert 时 Qdrant 要用到
        self.dim = len(self.embed("probe"))

    def embed(self, text: str) -> list:
        resp = self._client.embeddings.create(model=self.model, input=text)
        return resp.data[0].embedding


class LocalHashEmbedder(Embedder):
    """
    离线兜底：把文本里的词哈希到固定维度向量（词频加权）。
    虽然不如语义向量"懂意思"，但保证"没网络也能跑"，且仍是正经的向量相似度检索。
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, text: str) -> list:
        vec = [0.0] * self.dim
        # 极简分词：英文按空白、中文按字（演示够用）
        tokens = []
        for w in text.lower().split():
            tokens.append(w)
        for ch in text:
            if "\u4e00" <= ch <= "\u9fa5":
                tokens.append(ch)
        if not tokens:
            return vec
        for t in tokens:
            h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        # L2 归一化，方便之后用余弦相似度
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


def get_embedder() -> Embedder:
    """优先用真·OpenAI 语义向量；没配 key 或调用失败就退回本地哈希兜底。"""
    try:
        return OpenAIEmbedder()
    except Exception:
        return LocalHashEmbedder()
