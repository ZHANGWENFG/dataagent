# -*- coding: utf-8 -*-
"""
skills.py —— 技能系统（大白话版）
================================
对标 pydantic-deepagents 的 Skills：把"某个领域的固定打法"写成一份 SKILL.md，
Agent 遇到相关问题时，把这份技能说明注入 prompt，相当于给模型一份"操作手册"。

和 joyagent 的区别：joyagent 里没有 skills 这个概念（只有 tools + SOP），
所以这一步是你"集齐 skills 点"的关键补充。
"""

import os
import glob
from llm import ask

SKILL_DIR = os.path.join(os.path.dirname(__file__), "skills")


def load_skills() -> dict:
    """
    扫描 skills/ 目录下所有 SKILL.md，解析出 {技能名: 说明文本}。
    每份文件第一行写技能名，空一行后写正文（极简 frontmatter，方便你改）。
    """
    skills = {}
    for path in glob.glob(os.path.join(SKILL_DIR, "*.md")):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        name = lines[0].lstrip("# ").strip()      # 第一行当名字
        body = "\n".join(lines[1:]).strip()
        skills[name] = body
    return skills


def pick_skill(query: str, skills: dict) -> str:
    """
    给定一个用户问题，从所有技能里挑'最相关'的一份返回其正文。
    做法：把 query 和每份技能正文拼一起让 LLM 选名字；简单可靠。
    """
    if not skills:
        return ""
    listing = "\n".join(f"- {k}" for k in skills)
    sys = "你是技能路由。用户问题该用下面哪个技能？只回复技能名，不要解释。"
    choice = ask(f"可选技能：\n{listing}\n\n用户问题：{query}\n请选一个技能名：",
                 system=sys, temperature=0.0)
    return skills.get(choice.strip(), "")     # 没匹配上就返回空


# 模块加载时直接备好技能库，Agent 随用随取
SKILLS = load_skills()
