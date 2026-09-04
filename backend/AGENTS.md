# AGENTS.md — Backend 开发指南

本目录是 Document Copilot 的 FastAPI 后端。系统目标：让分析师用自然语言查询 SEC 披露文件语料，得到**有据可依、可溯源引用**的答案。信任契约是架构核心——每条事实性陈述都必须引用检索到的原文段落，语料不足时必须明确失败，绝不返回无据答案。

## 常用命令

所有命令在 `backend/` 目录下执行，依赖用 [uv](https://docs.astral.sh/uv/) 管理（`app/` 会以可编辑包安装，`from app...` 导入在所有场景可用）。

```bash
# 安装/同步依赖（Python 3.12+）
uv sync

# 启动本地 PostgreSQL + pgvector（pg16，端口 5432）
docker compose up -d postgres

# 应用数据库迁移（首次启动前执行）
uv run alembic upgrade head

# 生成迁移（改完 SQLAlchemy 模型后；务必人工审查 autogenerate 结果，
# 对 vector 列/tsvector/HNSW/GIN 等 Postgres 特性补显式 op.execute()）
uv run alembic revision --autogenerate -m "描述"

# 启动开发服务器（热重载，端口 8000）
uv run uvicorn app.main:app --reload

# 运行全部测试（不含集成测试）
uv run pytest

# 运行单个测试 / 单个文件
uv run pytest tests/ingest/test_chunker.py::test_name
uv run pytest tests/retrieval/test_retriever.py

# 仅运行需要真实数据库/OpenRouter 的集成测试
uv run pytest -m integration

# 运行单个集成测试
uv run pytest tests/retrieval/test_retriever.py -m integration

# Lint / 格式化
uv run ruff check .
uv run ruff format .

# 摄入语料（离线流水线，幂等可重跑；见 data/download.py 下载原始文件）
uv run -m ingest [downloads_dir]
```

环境变量见 `.env.example`（`DATABASE_URL`、`JWT_SECRET_KEY`、`OPENROUTER_API_KEY` 等）。集成测试会把 `DATABASE_URL` 切换到 `document_copilot_test` 库。

## 架构总览

后端有两条互不重叠的链路：

1. **摄入链路（离线，一次性脚本）**：`ingest/` 包，把 `data/downloads/manifest.json` 里的每份 SEC 文件「下载 → HTML 抽取 Markdown → 分块 → 向量化 → 写入 Postgres」。
2. **实时聊天链路（在线，HTTP 服务）**：`app/` 包，FastAPI 端点 → JWT 鉴权 → PydanticAI agent 自主检索 → 事实依据校验 → 流式返回带引用的答案并持久化。

两者通过**共享的嵌入客户端**（`app/core/embeddings.py`）和**共享的 Postgres 表**（`source_documents` / `document_chunks`）衔接：离线侧写库、在线侧检索，必须用同一模型和同一向量维度。

## 分层与模块职责

```
app/
├── main.py               # FastAPI 应用装配：CORS、挂载 auth/chat 路由
├── api/                  # 路由层（薄）：auth.py、chat.py
├── core/
│   ├── config.py         # Settings 单例（pydantic-settings），环境变量唯一入口
│   └── embeddings.py     # 共享嵌入客户端 get_embedding()，离线/在线共用
├── auth/                 # JWT 签发/校验、密码哈希、get_current_user 依赖、service
├── chat/                 # 线程/消息业务逻辑 + 整轮编排 + 流式事件
│   ├── service.py        # 线程 CRUD、answer_in_thread（权限校验→持久化问题→跑 agent→存答案）
│   ├── orchestrator.py   # answer_question：装配依赖并调 agent（持久化不在其职责内）
│   └── streaming.py      # 把 GroundedAnswer 编码为 AI SDK 兼容的 SSE 帧
├── assistant/            # LLM 边界（全项目唯一触达 LLM 的地方）
│   ├── agent.py          # PydanticAI agent + search_filings/read_chunks 工具 + output_validator
│   ├── deps.py           # DocumentAgentDeps 运行时依赖 dataclass
│   ├── outputs.py        # AnswerDraft/Citation/SourcePassage/GroundedAnswer 类型
│   ├── instructions.py   # agent 系统提示（产品契约写入此处）
│   └── model.py          # 构建 chat model（OpenRouter slug）
├── retrieval/
│   ├── retriever.py      # PgVectorRetriever：混合检索（向量 + 全文 + RRF）
│   └── rrf.py            # 倒数排名融合
├── grounding/
│   └── validator.py      # GroundingValidator：引用必须逐字落在检索段落内
└── database/
    ├── session.py        # async Engine/连接池/Session、get_session 依赖
    ├── models/           # SQLAlchemy 表模型（alembic autogenerate 的 source of truth）
    └── users.py / chat_threads.py / chat_messages.py / refresh_tokens.py  # 仓储函数
```

命名体现产品工作流而非泛化 service 层：`chat/orchestrator.py` 管一轮对话生命周期，`assistant/agent.py` 管 LLM 边界，`retrieval/` 管原文段落混合检索，`grounding/` 管「答案必须引用检索证据」这一信任契约。

## 核心机制

### Agent 工具循环（不是「检索一次再喂给 LLM」）

PydanticAI agent 自主决定检索时机，通过两个有边界的工具与语料交互：

- `search_filings(query)`：混合检索，返回每个 chunk 的**摘要**（`ChunkSummary`，只含前 240 字符 + 元数据），控制 token 成本。
- `read_chunks(chunk_ids)`：按 id 取完整 chunk 正文，并带上同文档相邻 chunk（跨 chunk 边界的引用也能逐字校验）。

每次工具返回的段落都被累加进 `deps.passages`，供输出校验阶段解析引用。agent 用 `@agent.output_validator` 强制执行 `grounding_validator.validate()`——这一步把 LLM 的草稿（`AnswerDraft`，只含 chunk_id 指针 + 引用文本）校验并还原成 `GroundedAnswer`（含完整 `cited_passages`），**违反事实依据即抛 `GroundingError` 使整轮失败**，而不是返回措辞漂亮但无据的答案。

### 混合检索 + RRF

`PgVectorRetriever.search()` 跑两条腿：pgvector 余弦相似度（`embedding <=> :vector`）和 Postgres 全文检索（`search_vector @@ websearch_to_tsquery`），用倒数排名融合（RRF）合并，再按 `top_k` 取回。两条腿按 `corpus_owner_email`（共享语料虚拟用户）过滤并排除软删文档。检索器刻意不依赖 PydanticAI，可独立测试。

### 事实依据（Grounding）契约

- 每条答案至少一条引用，除非明确声明证据不足（`evidence_sufficient=False`）。
- 每条引用必须对应本轮检索到的段落，且 `quote` 是段落正文的**逐字子串**（归一化空白、解码 HTML 实体后比对）。
- 引用指向相邻 chunk 的误指会被自动重绑到真正逐字匹配的段落，但任何无法逐字落地的引用都直接失败。
- 违反契约映射为受控的 `502`，绝不返回无据答案。

### 数据模型与权限

表：`users`、`chat_threads`、`chat_messages`、`refresh_tokens`、`source_documents`、`document_chunks`、`document_tables`、`message_citations`。行级隔离在应用层实现：所有按用户隔离的查询显式按 `user_id` 过滤；非属主资源返回 `404`（而非 `403`）以避免泄露资源存在性。语料文档归属一个系统虚拟用户 `corpus_owner_email`（`corpus@system.local`）。

### 摄入流水线（幂等）

`ingest/pipeline.py` 的 `ingest_corpus()` 按 `manifest.json` 逐文件处理：`completed` 状态的文档跳过，其他状态重建。check-then-insert 去重，因此**不可并发运行**（一次性脚本的单进程假设）。崩溃会在文档上留下 `processing`/`failed` 状态，下次运行可见并重建。流程：`extract_markdown`（HTML→Markdown）→ `chunk_markdown` → `get_embedding`（批量）→ 写入 `SourceDocument` + `DocumentChunk`。

### 配置

所有环境变量经 `app/core/config.py` 的 `Settings` 单例读取，**组件、路由、service 不得直接读环境变量**。OpenRouter key 在 settings 层可选（保证无 key 环境能跑快速测试），真正调用处用 `settings.require_openrouter_api_key()` 快速失败。嵌入维度须与 `EMBEDDING_DIMENSIONS` 一致，`get_embedding` 会校验上游返回宽度。

## 测试约定

根 `tests/conftest.py` 是关键的全局 fixture 来源：

- 它把 `DATABASE_URL` 覆盖为 `document_copilot_test`（在 `app.core.config` 被 import **之前**覆盖，否则缓存的 settings 单例会把开发库 URL 泄漏给 alembic 迁移）。
- 提供 `migrated_database` / `db_engine` / `session_factory` / `db_session` fixture（惰性求值：快速套件不触发建库）。
- 提供 `FakeEmbedder` / `fake_embedder`，用确定性伪向量替身 `get_embedding`，让摄入/检索/聊天测试无需真实 LLM。

约定：需要真实 Postgres 或 OpenRouter 的测试标 `@pytest.mark.integration`；`asyncio_mode = "auto"` 所以 async 测试函数无需 `@pytest.mark.asyncio`。agent 层通过注入假的 retriever/validator 和 mock model 做无数据库、无 LLM 的单元测试。
