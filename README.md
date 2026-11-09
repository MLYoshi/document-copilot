# Document Copilot

面向 SEC 披露文件的检索增强生成（RAG）问答应用。用户注册登录后，可以围绕已收录的公司文件提问，实时查看流式回答及对应引用，并管理自己的历史会话。

## 功能

- SEC 文件问答：基于已导入的披露文件检索相关段落，生成有依据的回答。
- 原文引用：回答附带引用，可展开查看引用原文。
- 流式输出：通过 SSE 逐段返回回答，减少等待时间。
- 用户认证：支持注册、登录、退出和令牌自动刷新。
- 历史会话：支持新建会话、查看会话列表及历史消息。
- 批量导入：将 HTML 文件提取为 Markdown，生成摘要与向量后写入数据库。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端 | React 18、TypeScript、Vite、Tailwind CSS、Radix UI |
| 后端 | Python 3.12、FastAPI、SQLAlchemy、Alembic |
| Agent | LangGraph、LangChain |
| 模型服务 | OpenRouter（对话、摘要及向量模型） |
| 数据存储 | PostgreSQL、pgvector |
| 身份认证 | Supabase Auth |
| 可观测性 | Langfuse（可选） |

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # 认证与会话接口
│   │   ├── assistant/    # LangGraph Agent 与结构化输出
│   │   ├── auth/         # Supabase 认证
│   │   ├── chat/         # 会话、消息及流式回答
│   │   ├── core/         # 配置、向量和摘要
│   │   ├── database/     # 数据模型与数据库会话
│   │   └── retrieval/    # pgvector 检索
│   ├── ingest/           # 文件解析、摘要、向量化及导入
│   └── alembic/          # 数据库迁移
├── frontend/
│   └── src/              # 页面、组件及 API 客户端
└── data/
    ├── downloads/        # 原始 HTML 与 manifest.json
    ├── markdown/         # 已转换的 Markdown 文件
    └── download.py       # 数据下载脚本
```

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 与 pnpm
- 已启用 `pgvector` 扩展的 PostgreSQL 数据库
- Supabase 项目
- OpenRouter API Key

## 配置

在 `backend/.env` 中配置后端环境变量：

```dotenv
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/document_copilot

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

OPENROUTER_API_KEY=your-openrouter-api-key
```

`SUPABASE_SERVICE_ROLE_KEY` 用于数据导入时创建或查找语料所有者，导入前必须配置。认证和会话功能仅使用 Supabase anon key。

常用可选配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CHAT_MODEL` | `minimax/minimax-m3:free` | OpenRouter 对话模型 |
| `SUMMARY_MODEL` | 与 `CHAT_MODEL` 相同 | 导入时生成摘要的模型 |
| `EMBEDDING_MODEL` | `baai/bge-m3` | OpenRouter 向量模型 |
| `EMBEDDING_DIMENSIONS` | `1024` | 向量维度，应与数据库字段一致 |
| `RETRIEVAL_TOP_K` | `8` | 每次检索返回的段落数 |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | 允许的前端来源，多个来源用逗号分隔 |
| `CORPUS_OWNER_EMAIL` | `corpus@system.local` | 语料所有者的 Supabase 用户邮箱 |
| `LANGFUSE_PUBLIC_KEY` | 无 | Langfuse 公钥 |
| `LANGFUSE_SECRET_KEY` | 无 | Langfuse 密钥 |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 服务地址 |

前端默认请求 `http://localhost:8000`。如需修改，在 `frontend/.env` 中配置：

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

请勿提交包含真实密钥的 `.env` 文件。

## 初始化与启动

### 1. 初始化后端

```bash
cd backend
uv sync
uv run alembic upgrade head
```

### 2. 导入 SEC 文件

在 `data/downloads/manifest.json` 的 `filings` 列表中配置文件元数据，并将对应 HTML 放入 `local_path` 指定的位置。每条记录需要包含：

- `ticker`、`cik`、`form`
- `filing_date`、`report_date`、`accession_number`
- `primary_document`、`local_path`
- `source_url`（可选）

从项目根目录执行：

```bash
cd backend
uv run python -m ingest ../data/downloads
```

仅导入单个文件：

```bash
uv run python -m ingest ../data/downloads --file path/to/filing.html
```

导入过程会提取 Markdown、生成摘要和向量，并将文件内容与元数据写入数据库。已经完成的文件会自动跳过。

### 3. 启动后端

```bash
cd backend
uv run uvicorn app.main:app --reload
```

- API 地址：http://localhost:8000
- Swagger 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 4. 启动前端

另开终端执行：

```bash
cd frontend
pnpm install
pnpm dev
```

访问 http://localhost:5173，注册并登录后即可开始提问。使用前请确保数据库中已经导入文件，并正确配置 OpenRouter。

## API 概览

除认证接口与健康检查外，以下接口均需要 `Authorization: Bearer <access_token>` 请求头。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/auth/register` | 注册用户 |
| `POST` | `/auth/login` | 登录并获取令牌 |
| `POST` | `/auth/refresh` | 刷新访问令牌 |
| `POST` | `/auth/logout` | 退出登录 |
| `GET` | `/auth/me` | 获取当前用户 |
| `GET` | `/threads` | 获取当前用户的会话列表 |
| `POST` | `/threads` | 创建会话 |
| `GET` | `/threads/{thread_id}` | 获取会话详情 |
| `GET` | `/threads/{thread_id}/messages` | 获取历史消息 |
| `POST` | `/threads/{thread_id}/messages/stream` | 发送问题并以 SSE 流式返回答案 |
| `GET` | `/health` | 健康检查 |

## 常用开发命令

```bash
# 后端代码检查
cd backend && uv run ruff check .

# 前端构建
cd frontend && pnpm build

# 前端代码检查
cd frontend && pnpm lint
```

> 回答仅基于当前已收录的 SEC 披露文件。请结合原始文件核验重要信息，不要将生成内容视为投资建议。
