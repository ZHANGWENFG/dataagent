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


def ask_stream(prompt: str, system: str = "你是一个有帮助的数据分析助手。",
              temperature: float = 0.0):
    """
    流式版 ask：用 OpenAI SDK 的 stream=True，逐 token yield 出来（像打字机）。
    上层（Streamlit 的 st.write_stream）可以直接消费这个生成器，做出流式观感。
    离线兜底：没 key / 调用失败时，退化成"整段作为单个 chunk 吐出"，保证仍是生成器、不崩。
    """
    try:
        client = _client()
    except RuntimeError:
        # 没 key：退化成整段（用非流式 ask 兜底，再失败就给占位文本）
        try:
            yield ask(prompt, system=system, temperature=temperature)
        except Exception:
            yield "（离线无 LLM key，无法流式生成）"
        return
    stream = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
