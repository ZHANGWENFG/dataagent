# -*- coding: utf-8 -*-
"""
sql_exec.py —— SQL 执行器（大白话版）
==================================
把"在示例库上跑一条 SQL"这件小事单独抽出来，让 mcp_server / tools / app(Streamlit)
三处共用同一份逻辑，避免到处复制粘贴。

约定：成功返回结果文本；失败直接抛异常（交给上层做"自检/反思"重试）。
"""

import sqlite3
import pandas as pd
from db import DB_PATH


def run_sql(sql: str) -> str:
    """用 pandas 在示例库上跑 SQL，转成易读文本（避免把整个 DataFrame 塞给模型）。"""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(sql, conn)
        return df.to_string(index=False) if not df.empty else "（无数据）"
    finally:
        conn.close()
