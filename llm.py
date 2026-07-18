# -*- coding: utf-8 -*-
"""
llm.py —— LLM 客户端封装（大白话版）
====================================
把"调大模型"这件麻烦事包一层，上层代码只管 ask("帮我干啥")。
用 OpenAI 官方 SDK，但它兼容 DeepSeek / 通义 等所有 OpenAI 格式的服务，
所以只要改 config 里的 BASE_URL 就能换厂商，不用动这里。
"""

from openai import OpenAI
from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL


def _client() -> OpenAI:
    """懒加载客户端：第一次真正调用才建连接，避免一导入就报错。"""
    if not LLM_API_KEY:
        raise RuntimeError(
            "❌ 没检测到 OPENAI_API_KEY。请先 export OPENAI_API_KEY=xxx 再运行。"
        )
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def ask(prompt: str, system: str = "你是一个有帮助的数据分析助手。",
        temperature: float = 0.0) -> str:
    """
    最简单的"问一句、答一句"。
    :param prompt: 用户问题 / 给模型的指令
    :param system: 系统人设
    :param temperature: 0.0=最稳（SQL 生成用这个），高一点=更发散（头脑风暴用）
    :return: 模型回复的文本
    """
    resp = _client().chat.completions.create(
        model=LLM_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content.strip()


def ask_json(prompt: str, system: str = "只输出 JSON，不要废话。") -> str:
    """专门给"要模型吐 JSON"的场景用（比如让模型挑字段）。"""
    return ask(prompt, system=system)
