# simple_data_agent —— 精简版纯 Python DataAgent

> 这是 **JoyAgent-JDGenie（DataAgent 分支）的"砍掉 DB-GPT 那堆重东西"后的最小可行版**。
> 只保留你需要的 4 块能力，每一行都带大白话中文注解，方便你对着真代码看懂、写进简历。

## 它保留了什么（ vs 庞大的 DB-GPT）

| 能力 | 对应文件 | 说明 |
|---|---|---|
| 智能问数 NL2SQL | `nl2sql.py` + `table_rag.py` + `embeddings.py` | **真·Qdrant 向量召回**两阶段选表选字段（`:memory:` 免起服务）+ LLM rerank + NL2SQL 三段式 |
| 诊断分析 归因 | `diagnose.py` | 趋势/异常/周期/相关性量化 + LLM 讲成人话 |
| 多 Agent 编排 harness | `agent.py` | BaseAgent + ReAct + Planning/Executor + Orchestrator 路由 |
| MCP + Skills 接入 | `tools.py` + `skills.py` | BaseTool 可插拔 + MCPTool 外部转发 + SKILL.md 技能系统 |

**砍掉了**：AWEL 图引擎、GraphRAG、微调 Hub、多数据库连接器、管理后台——这些对"看懂+简历"是负担。

## 目录结构

```
simple_data_agent/
├── config.py        # LLM 配置 + 示例表结构（= DGP 治理后的元数据）
├── llm.py           # LLM 客户端封装（OpenAI 格式，可换 DeepSeek）
├── embeddings.py    # 文本向量化：OpenAIEmbedder 真语义向量 + LocalHashEmbedder 离线兜底
├── db.py            # 生成确定性示例数据库（电商销售，含趋势+异常）
├── table_rag.py     # 两阶段选表 + 选字段（真·Qdrant 向量召回，:memory: 免起服务）
├── nl2sql.py        # NL2SQL 三段式
├── diagnose.py      # 诊断归因（pandas 量化 + LLM 叙述）
├── tools.py         # 工具系统：BaseTool + 内置工具 + MCPTool
├── skills.py        # 技能系统：扫描 skills/*.md 并按问题路由
├── agent.py         # harness：BaseAgent / ReAct / Planning / Orchestrator
├── main.py          # 命令行入口
├── skills/
│   ├── data_query.md   # 智能问数技能手册
│   └── diagnostic.md   # 诊断分析技能手册
└── requirements.txt
```

## 怎么跑（接真实 LLM）

```bash
cd simple_data_agent

# 1) 装依赖（建议用虚拟环境）
pip install -r requirements.txt

# 2) 配置 LLM（二选一）
export OPENAI_API_KEY="sk-xxx"
export OPENAI_BASE_URL="https://api.openai.com/v1"   # 想用 DeepSeek 换成它的地址
export MODEL="gpt-4o-mini"                            # 或 deepseek-chat

# 3) 运行（会自动建示例库 + 跑两个示例问题）
python main.py
# 或指定你自己的问题
python main.py "上月哪个城市销售额最高？"
```

## 面试怎么讲（一句话版）

> "我读 JoyAgent 的 DataAgent 分支后发现它 Java+Python 两层太重，就自己用纯 Python 重写了一个最小版：
> TableRAG 两阶段选表选字段 + NL2SQL 三段式做智能问数，pandas 量化+LLM 做诊断归因，
> 自研 BaseAgent harness 支持 ReAct / Plan-and-Execute 两种编排，工具用 BaseTool 可插拔、
> 通过 MCPTool 接外部服务、用 SKILL.md 做技能系统。整套零重依赖、接任意 OpenAI 格式大模型。"

## 下一步可以加（简历加分项）

- ✅ `table_rag.py` 已换成真·Qdrant 向量召回（`:memory:` 模式，OpenAIEmbedder 真语义向量 + 本地哈希兜底）—— 就是 joyagent 的原版 TableRAG 思想
- `tools.py` 里起一个真实 MCP Server，让 `MCPTool` 真正打通
- `agent.py` 的 PlanningAgent 改成"并行执行子任务"（对标 joyagent 的 CountDownLatch 扇出）
