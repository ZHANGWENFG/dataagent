# -*- coding: utf-8 -*-
"""
cache.py —— 查询缓存（大白话版）
================================
生产系统里"同一个问题被反复问"很常见，每次都调 LLM + 跑 SQL 又慢又烧钱。
这里做一个轻量查询缓存：把"归一化后的问题"当 key，第一次算完把结果存起来，
下次同样的问题直接返回缓存（命中即跳过 LLM + SQL），降本降延迟。
  · 内存 + SQLite 双保险：进程内快、还能跨重启保留
  · LRU 淘汰：超过容量删最久没用的
  · 默认 key 只留"字母/数字/中文"，忽略大小写和标点空白 —— 所以"北京销售额?"和"北京 销售额？"算同一问
"""

import re
import json
import time
import sqlite3


def normalize(query: str) -> str:
    """把问题归一化成缓存 key：转小写、去空白、只留字母数字中文。"""
    q = query.lower()
    q = re.sub(r"\s+", "", q)
    q = re.sub(r"[^\w\u4e00-\u9fff]", "", q)   # \w 含字母数字下划线，\u4e00-\u9fff 是常用汉字
    return q


class QueryCache:
    def __init__(self, path: str = ".query_cache.db", max_size: int = 200):
        self.path = path
        self.max_size = max_size
        self.conn = None          # 懒加载：import 时不建文件，第一次用才连库

    def _ensure(self):
        if self.conn is None:
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, ts REAL)")

    def get(self, query: str):
        """命中返回缓存的 dict，未命中返回 None。"""
        self._ensure()
        row = self.conn.execute("SELECT v FROM cache WHERE k=?", (normalize(query),)).fetchone()
        if row:
            # 刷新 ts，记为"最近用过"（LRU 用）
            self.conn.execute("UPDATE cache SET ts=? WHERE k=?", (time.time(), normalize(query)))
            self.conn.commit()
            return json.loads(row[0])
        return None

    def put(self, query: str, value: dict):
        """把结果存进缓存（value 必须是 JSON 可序列化 dict）。"""
        self._ensure()
        k = normalize(query)
        v = json.dumps(value, ensure_ascii=False)
        self.conn.execute("INSERT OR REPLACE INTO cache (k, v, ts) VALUES (?,?,?)",
                          (k, v, time.time()))
        self.conn.commit()
        self._evict()

    def _evict(self):
        """超过 max_size 就删最久没用过的。"""
        cnt = self.conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        if cnt > self.max_size:
            excess = cnt - self.max_size
            old = self.conn.execute(
                "SELECT k FROM cache ORDER BY ts ASC LIMIT ?", (excess,)).fetchall()
            for (k,) in old:
                self.conn.execute("DELETE FROM cache WHERE k=?", (k,))
            self.conn.commit()

    def clear(self):
        self._ensure()
        self.conn.execute("DELETE FROM cache")
        self.conn.commit()


# 全局默认缓存（UI / 工具 / CLI 都能共用同一个）
default_cache = QueryCache()
