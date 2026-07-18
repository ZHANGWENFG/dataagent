# simple_data_agent —— 精简版纯 Python DataAgent

> 这是 **JoyAgent-JDGenie（DataAgent 分支）的"砍掉 DB-GPT 那堆重东西"后的最小可行版**。
> 只保留你需要的 4 块能力，每一行都带大白话中文注解，方便你对着真代码看懂、写进简历。

## 它保留了什么（ vs 庞大的 DB-GPT）

| 能力 | 对应文件 | 说明 |
|---|---|---|
| 智能问数 NL2SQL | `nl2sql.py` + `table_rag.py` + `embeddings.py` | **混合召回**（BM25 关键词 + Qdrant 向量，RRF 融合）+ **LLM rerank 精排** 两阶段选表选字段（`:memory:` 免起服务）+ NL2SQL 三段式 + **自检/反思循环**（SQL 跑挂自动改 SQL 重试） |
| 诊断分析 归因 | `diagnose.py` | 趋势/异常/周期/相关性量化 + LLM 讲成人话 |
| 多 Agent 编排 harness | `agent.py` | BaseAgent + ReAct + **Planning 并行扇出**(ThreadPoolExecutor) + **DeepSearch 顺序多步推理闭环** + Orchestrator 三级路由 + **多轮对话记忆** |
| 查询缓存 | `cache.py` | 问题归一化→LRU→SQLite 持久化；相同/等价问题第二次直接命中，跳过 LLM+SQL（降本降延迟） |
| 业务知识库问答(SOP 召回) | `kb.py` + `knowledge/` | 问数/诊断前先从知识库 md 召回业务口径 SOP（BM25+向量双路+RRF 融合），注入提示避免"销售额"口径歧义；对齐 joyagent plan_sop |
| MCP + Skills 接入 | `tools.py` + `skills.py` + `mcp_server.py` | BaseTool 可插拔 + **真·MCP Server**（FastMCP 暴露 query_data/diagnose，stdio 真调用）+ SKILL.md 技能系统 |

**砍掉了**：AWEL 图引擎、GraphRAG、微调 Hub、多数据库连接器、管理后台——这些对"看懂+简历"是负担。

## 目录结构

```
simple_data_agent/
├── config.py        # LLM 配置 + 示例表结构（= DGP 治理后的元数据）
├── llm.py           # LLM 客户端封装（OpenAI 格式，可换 DeepSeek）
├── embeddings.py    # 文本向量化：OpenAIEmbedder 真语义向量 + LocalHashEmbedder 离线兜底
├── db.py            # 生成确定性示例数据库（电商销售，含趋势+异常）
├── sql_exec.py      # SQL 执行器（mcp_server / tools / app 三处共用，统一跑 SQL 的逻辑）
├── table_rag.py     # 两阶段选表 + 选字段（BM25+Qdrant 混合召回 + RRF 融合 + LLM rerank 精排，:memory: 免起服务）
├── nl2sql.py        # NL2SQL 三段式 + 自检/反思循环（跑挂自动改 SQL 重试）
├── diagnose.py      # 诊断归因（pandas 量化 + LLM 叙述）
├── tools.py         # 工具系统：BaseTool + 内置工具 + 真·MCP 客户端 + MCPTool
├── mcp_server.py    # 真·MCP Server（FastMCP）：暴露 query_data / diagnose 工具
├── skills.py        # 技能系统：扫描 skills/*.md 并按问题路由
├── agent.py         # harness：BaseAgent / ReAct / Planning / DeepSearch / Orchestrator（含多轮记忆）
├── deep_search.py   # 深度搜索：顺序多步推理闭环（拆解→逐步检索证据→反思→综合），区别于 Planning 并行扇出
├── memory.py        # 多轮对话记忆：ConversationMemory（追加轮次 + 历史上下文注入，解决指代追问）
├── cache.py         # 查询缓存：QueryCache（归一化 key + LRU + SQLite 持久化，命中即跳过 LLM+SQL）
├── kb.py            # 业务知识库问答：KnowledgeBase（BM25+向量双路+RRF 召回口径 SOP，对齐 joyagent plan_sop）
├── knowledge/       # 业务口径知识库（md）：metrics.md(销售额/城市/渠道/会员) + diagnostic.md(异常/相关性/趋势)
├── app.py           # Streamlit 可视化界面（智能问数 + 诊断分析 + 深度搜索三个标签页，共用会话记忆）
├── eval.py          # 离线评测集：固定问题量化"选表准确率 / SQL 可执行率"
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
- ✅ `tools.py` 已接**真·MCP Server**（`mcp_server.py`，FastMCP 暴露 query_data/diagnose，经 stdio 真调用；保留原 HTTP 转发 MCPTool 作对照）
- ✅ `agent.py` 的 PlanningAgent 已改成**并行执行子任务**（ThreadPoolExecutor 扇出 + as_completed 合并，对标 joyagent 的 CountDownLatch 扇出）
- ✅ `table_rag.py` 升级为**混合召回**（纯 Python BM25 关键词路径 + Qdrant 向量路径，RRF 倒数排名融合）—— 对标 joyagent 的 Qdrant(向量)+ES(关键词) 双路，离线零依赖也能跑
- ✅ 混合召回之后再加一层 **LLM rerank 精排**：向量+BM25 负责"捞得全"，LLM 负责"排得准"；没配 key / 调用失败自动退回融合顺序，离线零依赖不崩

## 后续还能加（已规划，按需递进）
- ✅ `nl2sql.py` 已加 **NL2SQL 自检/反思循环**：生成 SQL → 执行 → 报错则把错误回喂 LLM 改 SQL 再试（对齐 joyagent 的 self-correction）；没 key 自动跳过重试，离线零依赖不崩
- ✅ 新增 **Streamlit 可视化界面**（`app.py`）：智能问数 + 诊断分析两个标签页，业务逻辑(run_query/run_diagnose)与界面分离便于单测；没 key 时界面照常打开并弹提示。SQL 执行抽成 `sql_exec.py` 由 mcp_server/tools/app 共用
- ✅ 新增 **离线评测集**（`eval.py`）：固定 7 道问数题，离线量化"选表准确率 / SQL 可执行率"（无需 LLM key）；设了 `OPENAI_API_KEY` 自动切换真实 NL2SQL 评测。本次实测 选表 7/7、可执行 7/7
- ✅ 新增 **GitHub Actions CI**（`.github/workflows/ci.yml`）：push/PR 自动装依赖 → py_compile 语法检查 → 全模块 import 检查 → 跑 `eval.py` 离线评测（无需密钥），保证改动不破坏主链路
- ✅ 新增 **DeepSearch 深度搜索**（`deep_search.py` + `agent.py` 的 `DeepSearchAgent` + `app.py` 第三个标签页）：顺序多步推理闭环——拆解子问题→逐步调工具拿证据→反思证据够不够→综合答案；区别于 PlanningAgent 的并行扇出，更贴近人做调研；Orchestrator 三级路由（深度/根因/综合→DeepSearch，分析→Planning，查数→ReAct）
- ✅ 新增 **多轮对话记忆**（`memory.py` + `agent.py` Orchestrator 持有 `ConversationMemory` + `app.py` 三标签页共用 `st.session_state.mem` 并带"新对话"按钮）：新问题进来把"历史对话"拼成上下文注入，解决"那北京呢？"指代追问；`main.py` 加 `--chat` 交互多轮模式。面试常问"你的 Agent 有状态吗"——有
- ✅ 新增 **查询缓存**（`cache.py` + `app.py` 三个纯函数接入 `default_cache`）：问题归一化（忽略大小写/标点/空白）作 key，LRU + SQLite 持久化；相同/等价问题第二次直接命中、跳过 LLM+SQL，界面显示"✅ 命中查询缓存"。降本降延迟，生产系统标配
- ✅ 新增 **业务知识库问答 / SOP 召回**（`kb.py` + `knowledge/*.md` + 注入 `nl2sql` 的 think/convert 与 `diagnose`）：问数/诊断前先从知识库召回业务口径 SOP（BM25+向量双路+RRF 融合），注入提示避免"销售额含不含退款"这类口径歧义；对齐 joyagent 的 plan_sop（已核验真有）。界面问数页展示"📚 命中业务口径"
- ⬜ 计划：流式输出（待补上）
