# -*- coding: utf-8 -*-
"""
tools.py —— 工具系统（大白话版）
================================
对标 joyagent 的 BaseTool 接口 + MCP 接入。
设计很简单：所有工具都实现 BaseTool（名字/描述/参数/执行），
Agent 不知道工具内部怎么干，只管"按名字调用 + 拿结果"。
MCPTool 则演示"工具不在本地、通过 HTTP 转发到外部 MCP 服务"的接入方式。
"""

import sqlite3
import requests
from abc import ABC, abstractmethod
from db import DB_PATH
from nl2sql import nl2sql
from diagnose import analyze


# ---------------- 工具基类：所有工具都要长这样 ----------------
class BaseTool(ABC):
    name: str = ""                 # 工具名（Agent 靠它识别）
    description: str = ""          # 工具是干啥的（写给 LLM 看的）
    params: dict = {}              # 参数定义（json schema 风格）

    @abstractmethod
    def run(self, **kwargs) -> str:
        """真正干活的地方，返回文本结果。"""
        ...


# ---------------- 内置工具 1：智能问数（NL2SQL + 执行）----------------
class DataQueryTool(BaseTool):
    name = "data_query"
    description = "把自然语言问题转成 SQL 并在销售库上执行，返回查询结果。用于'查数据/问数'类问题。"
    params = {"query": "用户的自然语言问题，例如'上月销售额最高的是哪个商品'"}

    def run(self, query: str = "", **kwargs) -> str:
        plan = nl2sql(query)                       # 三段式生成 SQL
        sql = plan["sql"]
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = pd_read(sql, conn)              # 执行真实 SQL
            conn.close()
            return f"[生成的SQL]\n{sql}\n[执行结果]\n{rows}"
        except Exception as e:
            return f"[SQL]\n{sql}\n[执行出错] {e}（可把错误回喂给模型重试）"


def pd_read(sql, conn) -> str:
    """用 pandas 跑 SQL 并转成易读文本（避免把整个 DataFrame 塞给模型）。"""
    import pandas as pd
    df = pd.read_sql_query(sql, conn)
    return df.to_string(index=False) if not df.empty else "（无数据）"


# ---------------- 内置工具 2：诊断分析 ----------------
class DiagnosticTool(BaseTool):
    name = "diagnostic"
    description = "对销售数据做趋势/异常/周期/相关性诊断，输出业务结论。用于'为什么/分析一下'类问题。"
    params = {"query": "用户的诊断诉求，例如'分析一下最近销售额异常的原因'"}

    def run(self, query: str = "", **kwargs) -> str:
        res = analyze(query)
        return f"[量化指标] {res['insights']}\n[结论] {res['conclusion']}"


# ---------------- MCP 工具：演示"外部工具接入" ----------------
class MCPTool(BaseTool):
    """
    对齐 joyagent 的 McpTool：工具逻辑不在本地，而是转发到外部 MCP 服务。
    真实项目里这里用 SSE/stdio 连 MCP Server；这里用 HTTP POST 演示同样的思想。
    没起外部服务时，返回提示而非崩溃——保证主链路永远能跑。
    """

    def __init__(self, name: str, url: str, description: str = "外部 MCP 工具"):
        self.name = name
        self.description = description
        self.url = url

    def run(self, **kwargs) -> str:
        try:
            r = requests.post(self.url, json=kwargs, timeout=5)
            return r.text
        except Exception as e:
            return f"[MCP {self.name} 未连接] {e}（这是演示接入点，启动对应 MCP Server 即可生效）"


# ---------------- 工具箱：统一管理本地 + MCP 工具 ----------------
class ToolCollection:
    """对标 joyagent 的 ToolCollection：Agent 手里的'工具抽屉'。"""

    def __init__(self):
        self.tools = {}                 # 本地 BaseTool
        self.mcp_tools = {}             # 外部 MCP 工具
        # 内置两个核心工具
        for t in (DataQueryTool(), DiagnosticTool()):
            self.tools[t.name] = t

    def add_mcp(self, tool: MCPTool):
        self.mcp_tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        return self.tools.get(name) or self.mcp_tools.get(name)

    def names(self) -> list:
        return list(self.tools.keys()) + list(self.mcp_tools.keys())

    def describe_for_llm(self) -> str:
        """把工具清单拼成文本，喂给 LLM 让它知道'能调哪些工具'。"""
        lines = []
        for t in list(self.tools.values()) + list(self.mcp_tools.values()):
            lines.append(f"- {t.name}: {t.description}")
        return "\n".join(lines)
