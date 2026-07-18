# -*- coding: utf-8 -*-
"""
memory.py —— 多轮对话记忆（大白话版）
====================================
对标真实 Agent 的"会话状态"：用户连着问好几轮时，Agent 得记得上一轮聊了啥，
否则"那北京呢？""为什么？"这种指代 / 追问就接不住。
这里用一个超轻量的 ConversationMemory 维护 {user, assistant} 轮次，
并在新问题进来时把"历史对话"拼成上下文块注入，让 LLM 做指代消解。
"""

class ConversationMemory:
    def __init__(self, max_turns: int = 10):
        self.turns = []          # [{role: "user" / "assistant", "content": str}]
        self.max_turns = max_turns

    def add(self, role: str, content: str):
        """记一轮：role 是 user 或 assistant。"""
        self.turns.append({"role": role, "content": content})
        # 只保留最近 max_turns 轮（一轮 = 1 user + 1 assistant）
        keep = self.max_turns * 2
        if len(self.turns) > keep:
            self.turns = self.turns[-keep:]

    def context_text(self) -> str:
        """把历史拼成一段可读文本；没历史返回空串。"""
        if not self.turns:
            return ""
        lines = []
        for t in self.turns:
            who = "用户" if t["role"] == "user" else "助手"
            lines.append(f"{who}：{t['content']}")
        return "\n".join(lines)

    def augment(self, query: str) -> str:
        """
        把历史对话作为上下文块，拼到当前问题前面。
        用清晰分隔，让 LLM 知道"前面聊过啥"，但重点仍是答当前问题（解决指代消解）。
        """
        ctx = self.context_text()
        if not ctx:
            return query
        return (f"【历史对话】\n{ctx}\n\n"
                f"【当前问题】\n{query}\n\n"
                f"（请结合历史对话理解当前问题里的指代 / 省略，只回答当前问题。）")

    def reset(self):
        self.turns = []
