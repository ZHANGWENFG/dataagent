# -*- coding: utf-8 -*-
"""
mcp_server.py —— 真·MCP Server（大白话版）
=========================================
用官方 mcp SDK 的 FastMCP 起一个标准 MCP Server，把两个核心能力暴露成 MCP 工具：
  - query_data ：自然语言问数（NL2SQL + 在 demo.db 上执行）
  - diagnose   ：对销售数据做诊断归因
任何支持 MCP 的客户端（Claude Desktop、Cursor、自研 Agent）都能连上来调用，
这就是 joyagent 里"工具逻辑不在本地、由外部 MCP Server 提供"的标准落地方式。

运行：python mcp_server.py        # 默认 stdio 传输，客户端拉起子进程通信
"""

import sqlite3
import pandas as pd
from mcp.server.fastmcp import FastMCP

from db import build, DB_PATH
from nl2sql import nl2sql
from diagnose import analyze

mcp = FastMCP("simple-data-agent")


def _run_sql(sql: str) -> str:
    """用 pandas 在示例库上跑 SQL，转成易读文本。"""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(sql, conn)
        return df.to_string(index=False) if not df.empty else "（无数据）"
    finally:
        conn.close()


@mcp.tool()
def query_data(question: str) -> str:
    """把自然语言问题转成 SQL 并在销售库上执行，返回查询结果。用于'查数据/问数'类问题。"""
    build()  # 确保示例库存在
    plan = nl2sql(question)
    try:
        return f"[生成的SQL]\n{plan['sql']}\n[执行结果]\n{_run_sql(plan['sql'])}"
    except Exception as e:
        return f"[SQL]\n{plan['sql']}\n[执行出错] {e}"


@mcp.tool()
def diagnose(question: str) -> str:
    """对销售数据做趋势/异常/周期/相关性诊断，输出业务结论。用于'为什么/分析一下'类问题。"""
    build()
    res = analyze(question)
    return f"[量化指标] {res['insights']}\n[结论] {res['conclusion']}"


if __name__ == "__main__":
    mcp.run()   # stdio 模式：从 stdin/stdout 和 MCP 客户端通信
