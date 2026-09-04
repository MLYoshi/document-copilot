# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

# Document Copilot

面向内部分析师（虚构客户 Driftwood Capital）的 AI 问答机器人：分析师用自然语言查询 SEC 披露文件（10-K/10-Q）语料，得到**有据可依、可溯源引用**的答案。

**信任契约是架构核心**：每条事实性陈述都必须引用检索到的原文段落；语料不足时必须明确失败（`evidence_sufficient=False`），绝不返回无据答案。宁可没有答案，也不给「自信但错误」的答案。

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.12+ + FastAPI + Uvicorn |
| LLM 编排 | PydanticAI（类型化 agent），OpenAI SDK 经 OpenRouter 网关调用 |
| 前端 | Vite + React SPA + TypeScript（严格模式），**不是 Next.js** |
| UI | Tailwind CSS + shadcn/ui |
| 数据库 | PostgreSQL + pgvector（语义检索）+ Postgres 全文检索 |
| 迁移 | SQLAlchemy 模型 + Alembic |
| 认证 | FastAPI 自实现 JWT（邮箱 + 密码），无第三方 Auth/OAuth |
| 依赖管理 | 后端 `uv`，前端 `pnpm` |

## 常用命令

### 后端（在 `backend/` 下执行，依赖由 `uv` 管理，`app/` 作为可编辑包安装）

```bash
uv sync                                              # 安装/同步依赖
docker compose up -d postgres                        # 启动本地 pg16 + pgvector（端口 5432）
uv run alembic upgrade head                          # 应用迁移（首次启动前）
uv run alembic revision --autogenerate -m "描述"      # 改完模型后生成迁移（务必人工审查，vector/tsvector/HNSW/GIN 需显式 op.execute()）
uv run uvicorn app.main:app --reload                 # 开发服务器（热重载，端口 8000）
uv run pytest                                        # 全部测试（不含集成测试）
uv run pytest tests/ingest/test_chunker.py::test_name  # 单测
uv run pytest -m integration                         # 仅集成测试（需真实 DB/OpenRouter）
uv run ruff check . && uv run ruff format .          # lint / 格式化
uv run -m ingest [downloads_dir]                     # 摄入语料（离线幂等流水线）
```

### 前端（在 `frontend/` 下执行，**只用 pnpm**，锁文件 `pnpm-lock.yaml`）

```bash
pnpm install      # 安装依赖
pnpm dev          # 开发服务器
pnpm build        # tsc -b && vite build
pnpm tsc --noEmit # 类型检查
pnpm lint         # eslint
```

### 数据下载（仓库根目录）

```bash
uv run data/download.py   # 从 SEC EDGAR 下载最新 5 份 10-K（AAPL/MSFT/NVDA/AMZN/GOOGL），gitignored
```

## 架构总览

后端有两条**互不重叠的链路**：

1. **摄入链路（离线，一次性脚本）**：`ingest/` 包，按 `data/downloads/manifest.json` 逐文件「下载 → HTML 抽取 Markdown → 分块 → 向量化 → 写入 Postgres」。幂等可重跑，check-then-insert 去重，**不可并发运行**。
2. **实时聊天链路（在线 HTTP 服务）**：`app/` 包，FastAPI 端点 → JWT 鉴权 → PydanticAI agent 自主检索 → 事实依据校验 → 流式返回带引用答案并持久化。

两者通过**共享的嵌入客户端**（`app/core/embeddings.py` 的 `get_embedding()`）和**共享的 Postgres 表**（`source_documents` / `document_chunks`）衔接：离线侧写库、在线侧检索，必须用同一嵌入模型和同一向量维度（默认 `baai/bge-m3`，1024 维）。

```text
分析师 → React SPA（Vite）--JWT Bearer--> FastAPI
                                          ├── PostgreSQL（users/chats/documents/chunks + pgvector + 全文）
                                          ├── Redis（缓存/会话状态）
                                          └── OpenRouter（LLM + 嵌入）
SEC 语料 --摄入流水线--> 嵌入 --> PostgreSQL
```

### 后端分层（`backend/app/`）

命名体现产品工作流而非泛化 service 层：

- `main.py` — FastAPI 装配（CORS、挂载 auth/chat 路由）
- `api/` — 薄路由层（`auth.py`、`chat.py`）
- `core/config.py` — `Settings` 单例（pydantic-settings），**环境变量唯一入口**，组件不得直接读环境变量
- `core/embeddings.py` — 共享嵌入客户端，离线/在线共用
- `auth/` — JWT 签发/校验、密码哈希、`get_current_user` 依赖、service
- `chat/` — 线程/消息业务逻辑 + 一轮对话编排 + 流式事件（`service.py`、`orchestrator.py`、`streaming.py`）
- `assistant/` — **LLM 边界（全项目唯一触达 LLM 的地方）**：`agent.py`（PydanticAI agent + 工具 + output_validator）、`deps.py`、`outputs.py`、`instructions.py`（产品契约写入系统提示）、`model.py`
- `retrieval/` — `retriever.py`（混合检索：pgvector 向量 + 全文 + RRF）、`rrf.py`
- `grounding/validator.py` — 引用必须逐字落在检索段落内
- `database/` — `session.py`（异步 Engine/连接池）、`models/`（SQLAlchemy 表模型，Alembic autogenerate 的 source of truth）、各仓储函数

### Agent 工具循环（不是「检索一次喂给 LLM」）

PydanticAI agent 通过两个有边界工具与语料交互：`search_filings(query)` 返回 chunk **摘要**（前 240 字符 + 元数据，控制 token），`read_chunks(chunk_ids)` 取完整正文 + 相邻 chunk。每次工具返回的段落累加进 `deps.passages`。`@agent.output_validator` 强制执行 `grounding_validator.validate()`，把 `AnswerDraft`（chunk_id 指针 + 引用文本）校验还原成 `GroundedAnswer`（含完整 `cited_passages`）。违反事实依据即抛 `GroundingError`，整轮失败映射为受控 `502`，而非返回无据答案。

### 混合检索 + RRF

`PgVectorRetriever.search()` 跑两条腿：pgvector 余弦相似度（`embedding <=> :vector`）和 Postgres 全文检索（`search_vector @@ websearch_to_tsquery`），用倒数排名融合（RRF）合并后取 `top_k`。按 `corpus_owner_email` 过滤共享语料、排除软删文档。检索器刻意不依赖 PydanticAI，可独立测试。

### 数据模型与权限

表：`users`、`chat_threads`、`chat_messages`、`refresh_tokens`、`source_documents`、`document_chunks`、`document_tables`、`message_citations`。**行级隔离在应用层实现**：所有按用户隔离的查询显式按 `user_id` 过滤；非属主资源返回 `404`（而非 `403`）以避免泄露资源存在性。语料文档归属系统虚拟用户 `corpus_owner_email`（`corpus@system.local`）。

### 认证端点

`POST /auth/register`、`POST /auth/login`、`POST /auth/refresh`、`POST /auth/logout`、`GET /me`。收到 `401` 时前端刷新 access token，失败则跳登录。

## 前端约定（`frontend/`）

- **纯 React SPA**（Vite + TypeScript 严格模式）。**不要提议 Next.js、SSR、服务端组件或文件路由**。
- 只用 `pnpm`。`.npmrc` 配置 `minimum-release-age=10080`（7 天），防御发布包投毒；确有紧急安全修复需覆盖时单次覆盖并在提交说明理由。
- **不写前端测试**（不要 `*.test.ts(x)`、不引入 vitest/Playwright/Cypress）。靠 `pnpm tsc --noEmit` + `pnpm lint` + 浏览器手动验证。
- 依赖策略：HTTP 用 `src/lib/http.ts` + `src/lib/api.ts`（原生 `fetch`，不用 axios/ky）；日期用原生 `Date`/`Intl`；不用 lodash；状态优先 `useState`/`useReducer`/`useContext`；表单用原生 `<form>` + `FormData`。
- UI 组件通过 `pnpm dlx shadcn@latest add <name>` 添加，不手写 shadcn 已有的东西。
- 目录：`src/components/`（shadcn 基础组件在 `components/ui/`）、`src/auth/`（`api.ts` 认证调用、`auth.ts` token 存取与刷新、`types.ts`）、`src/lib/`（`http`、`api`、`env`）、`src/pages/`（路由级组件）、`src/chat/`、`App.tsx`（路由）。
- 导入统一用 `@/*` 别名。
- 所有环境变量经 `src/lib/env.ts` 读取并在启动时校验（`VITE_` 前缀，如 `VITE_API_BASE_URL`），**绝不在组件中直接读 `import.meta.env.X`**。
- 后端对接：始终用 `@/lib/api` 的 `api.get/post/put/patch/delete`（负责 base URL、JWT bearer 注入、超时、带 `isNetworkError` 的 `ApiError`）；token 绝不通过组件 props 传递。

## 关键不变式（改动时必须遵守）

- 每条答案至少一条引用，除非明确声明证据不足；`quote` 必须是段落正文的**逐字子串**（归一化空白、解码 HTML 实体后比对），无法逐字落地的引用直接失败。
- 模型不能引用本次请求未检索到的文档。
- 配置：后端只经 `app/core/config.py`，前端只经 `src/lib/env.ts`；OpenRouter key 在 settings 层可选，真正调用处用 `settings.require_openrouter_api_key()` 快速失败。
- 嵌入维度须与 `EMBEDDING_DIMENSIONS` 一致，`get_embedding` 校验上游返回宽度。
- 迁移中 `create extension if not exists vector`、`vector(1024)` 列、生成 `tsvector` 列、HNSW/GIN 索引须用 `op.execute()` 显式书写。

## 测试约定（后端）

根 `tests/conftest.py` 是全局 fixture 来源：在 `app.core.config` 被 import **之前**把 `DATABASE_URL` 覆盖为 `document_copilot_test`（否则缓存的 settings 单例会泄漏开发库 URL）；提供 `migrated_database`/`db_engine`/`session_factory`/`db_session`（惰性求值）；提供 `FakeEmbedder`/`fake_embedder` 用确定性伪向量替身 `get_embedding`，让摄入/检索/聊天测试无需真实 LLM。需要真实 Postgres 或 OpenRouter 的测试标 `@pytest.mark.integration`；`asyncio_mode = "auto"`，async 测试函数无需 `@pytest.mark.asyncio`。agent 层通过注入假 retriever/validator 和 mock model 做无库无 LLM 单元测试。

## 权威文档

- `docs/architecture.zh-CN.md` — 目标架构（source of truth）
- `docs/client-brief.md` — 客户一页纸（含 10 道示例分析师问题）
- `docs/guides/backend-setup.zh-CN.md`、`docs/guides/frontend-setup.zh-CN.md` — 环境搭建
- `backend/AGENTS.md`、`frontend/AGENTS.md` — 子目录级详细约定

> 注意：`frontend/AGENTS.md` 开头引用的根级 `../AGENTS.md` 已不存在，本文件即为其替代。实施顺序见 `docs/architecture.zh-CN.md` 的「实施顺序」，不要一开始同时改数据库、Auth、前端、RAG。
