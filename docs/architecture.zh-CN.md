# Document Copilot 架构

## 目标

Document Copilot 是面向分析师的内部研究助手，帮助他们从经过整理的 SEC 披露文件语料中获得有据可依的答案。架构必须围绕「可信」进行优化：每个答案都由检索到的原文段落生成，每条事实性陈述都可溯源引用，并且当语料不支持某个答案时，系统要给出明确的失败反馈。

本文档描述聊天体验、LLM 编排，以及 React SPA 与 FastAPI 后端之间通信层的目标架构。

## 总体架构

开篇最合适的图是一张服务级视图，展示两条核心链路：直接服务用户的实时聊天链路，以及为检索准备 SEC 文件的摄入链路。

```mermaid
flowchart LR
    user[分析师] --> browser[浏览器<br/>React 聊天应用]

    subgraph infra[Railway / 云服务器]
        frontend[前端服务<br/>Vite 构建]
        backend[后端服务<br/>FastAPI + PydanticAI<br/>JWT 认证]
        redis[(Redis<br/>缓存 / 会话状态)]
        db[(PostgreSQL<br/>users、chats、documents、chunks<br/>pgvector + 全文检索)]
    end

    openrouter[OpenRouter 网关<br/>LLM + 嵌入模型]
    corpus[SEC 披露文件语料]
    ingestion[摄入流水线<br/>下载、解析、分块、向量化]

    frontend -->|提供应用| browser
    browser -->|POST /auth/login| backend
    backend -->|JWT access token| browser
    browser -->|聊天请求 + Bearer JWT| backend
    backend -->|检索段落<br/>持久化会话与引用| db
    backend -->|缓存| redis
    backend -->|查询向量化| openrouter
    backend -->|生成有据可依的答案| openrouter
    backend -->|流式返回答案与引用| browser

    corpus --> ingestion
    ingestion -->|创建嵌入向量| openrouter
    ingestion -->|存储文档与分块| db
```

等价的分层视图：

```text
                    ┌──────────────┐
                    │   分析师     │
                    └──────┬───────┘
                           ↓
                    React + Vite
                           │
                     JWT Bearer
                           ↓
                    FastAPI Backend
                           │
          ┌────────────────┼────────────────┐
          ↓                ↓                ↓
      PostgreSQL         Redis            OpenRouter
          │
      ┌───┴───────────┐
      │               │
   普通数据         pgvector
      │               │
 users/documents   embeddings
 chats/chunks      HNSW
 message_citations
```

通信链路：

```text
React
  ↓
FastAPI
  ├── JWT / Auth
  ↓
PostgreSQL + pgvector
```

## 架构目标

- 浏览器保持轻薄：只负责渲染聊天状态、保存自己的 JWT token，以及流式接收助手回复。
- 后端保持权威：认证、检索、事实依据校验、引用校验、工具执行和数据库写入全部发生在 FastAPI 中。
- 使用自管的 PostgreSQL 承载身份与持久化的产品状态：用户、会话线程、源文档、分块、嵌入向量和引用元数据。
- 使用 PostgreSQL `pgvector` 做语义检索，使用 Postgres 全文检索做关键词检索。
- 通过 PydanticAI agent 和显式的依赖、输出与工具边界，让 LLM 链路具备类型化和可测试性。
- 部署模型：Railway 或云服务器上运行前端、后端和 PostgreSQL；开发环境用 Docker Compose。

## 技术栈

前端：

- Vite + React SPA + TypeScript
- React Router 负责路由
- Tailwind CSS 与 shadcn/ui 负责 UI
- 自研 `src/auth/` 模块负责登录与 token 管理
- Vercel AI SDK 的 UI 包负责聊天状态与流式客户端行为

后端：

- Python 3.12+
- FastAPI + Uvicorn
- Pydantic v2 + pydantic-settings
- PydanticAI 负责类型化的 LLM 编排
- OpenAI SDK 负责生成与嵌入，统一通过 OpenRouter 网关调用（`base_url` 指向 OpenRouter，而非 OpenAI 直连）
- SQLAlchemy（asyncpg 驱动）负责数据库访问
- SQLAlchemy 模型 + Alembic 迁移负责 schema 管理
- PostgreSQL `pgvector` 负责语义检索
- Postgres 全文检索负责字面量检索
- JWT 签发与校验、密码哈希在 FastAPI 内实现
- `httpx` 负责出站 HTTP
- `structlog` 负责结构化日志

持久化：

- 自管 PostgreSQL 负责用户记录、会话线程、聊天消息、源文档、分块、嵌入向量、全文检索向量和引用元数据
- `pgvector` 扩展 + HNSW 索引承载向量检索

## 系统边界

前端负责用户交互、本地 UI 状态，以及把已认证用户的请求发送给后端。它持有用户自己的 JWT access token，绝不能持有任何特权凭据、运行检索逻辑，或直接调用 OpenRouter。

后端负责注册/登录、JWT 签发与校验、密码哈希、请求鉴权、检索、提示词构建、LLM 执行、引用校验、流式响应和持久化存储。它持有数据库连接串和 OpenRouter key 等全部特权凭据。

PostgreSQL 是唯一的事实存储。访问全部经由后端的 SQLAlchemy 连接池完成——浏览器和前端永远不直接连数据库。

## 认证与授权

认证与授权由 FastAPI 自有方案实现，身份与持久化状态全部存放在自管 PostgreSQL 中。

认证链路：

```text
React
 ↓
POST /auth/login
 ↓
FastAPI
 ↓
PostgreSQL 查询用户
 ↓
JWT
 ↓
React 保存 access_token
 ↓
以后每次请求 Authorization: Bearer xxx
```

认证端点：

```text
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /me
```

后端认证能力分为三块：

```text
FastAPI
 ├── JWT 签发与校验（auth/jwt.py）
 ├── password hashing（auth/password.py）
 └── current_user dependency（auth/dependencies.py）
```

`get_current_user` 的概念形态：

```python
async def get_current_user(
    token: str = Depends(oauth2_scheme)
):
    payload = decode_jwt(token)
    user_id = payload["sub"]
    return await user_repository.get(user_id)
```

所有需要身份的路由通过依赖注入拿到当前用户：

```python
@router.post("/chat/stream")
async def chat(
    current_user: User = Depends(get_current_user)
):
    ...
```

这样整个后端的用户身份就掌握在我们自己手里：用户记录存放在 PostgreSQL 的 `users` 表中，密码哈希由后端负责，JWT 由后端签发并由后端校验。

## 请求流程

1. 用户在 React SPA 中通过 `POST /auth/register` 注册、`POST /auth/login` 登录。
2. FastAPI 查询 PostgreSQL 中的用户记录、校验密码哈希，签发 JWT；前端把 access token 保存下来。
3. 用户打开某个会话时，前端通过 FastAPI 加载线程和历史消息，FastAPI 从 PostgreSQL 读取用户级记录。
4. 聊天 UI 使用 Vercel AI SDK 的 React 原语管理消息状态，并把新的用户消息提交给 FastAPI 聊天端点。
5. 前端以 `Authorization: Bearer <token>` 的形式发送 JWT。
6. 在进行任何检索或 LLM 工作之前，FastAPI 通过 `get_current_user` 校验 JWT 并解析出用户。
7. FastAPI 创建请求级上下文，其中包含已认证用户、会话线程、数据库 session、检索服务、引用策略和 LLM 设置。
8. PydanticAI agent 检索相关文档分块，生成有据可依的答案，并返回包含答案文本与引用的类型化输出。
9. FastAPI 以 AI SDK 客户端期望的格式，把助手消息分片流式返回给浏览器。
10. FastAPI 把最终的用户消息、助手消息、被引用的分块和用量元数据持久化到 PostgreSQL。

## 前端聊天层

前端保持为一个普通的 Vite SPA。不应引入 Next.js 的 route handler 或服务端组件。AI SDK 仅用于其 React 聊天原语和流式客户端行为。

聊天模块应按以下职责组织：

- `src/lib/env.ts` 校验 `VITE_API_BASE_URL`。
- `src/auth/api.ts` 封装注册、登录、刷新等认证调用。
- `src/auth/auth.ts` 管理 token 的保存、读取与刷新。
- `src/auth/types.ts` 认证相关类型。
- `src/lib/http.ts` 封装 `fetch`，应用后端 base URL、注入 bearer token、处理超时，并把失败转换为类型化的 API 错误。
- `src/lib/api.ts` 暴露产品级调用，例如加载线程、创建线程和拉取消息历史。
- `src/pages/chat/*` 渲染聊天路由，并把聊天流转发给一个职责单一的聊天组件。
- `src/components/chat/*` 渲染消息、引用、原文段落、空状态和流式状态。

API 请求统一携带 JWT：

```ts
fetch("/api/chat/stream", {
  headers: {
    Authorization: `Bearer ${token}`,
  },
});
```

聊天组件应使用已存储的消息进行初始化，然后由 AI SDK 管理进行中的 UI 状态。transport 指向 FastAPI，而不是前端的服务端路由。

概念形态：

```ts
const { messages, sendMessage, status, error } = useChat({
  id: threadId,
  messages: initialMessages,
  transport: new DefaultChatTransport({
    api: `${apiBaseUrl}/chat/stream`,
    headers: async () => ({
      Authorization: `Bearer ${await getAccessToken()}`,
    }),
  }),
});
```

具体 API 形态应在实现时对照已安装的 AI SDK 版本进行确认。架构层面的规则是稳定的：浏览器带着自己签发的 JWT 向 FastAPI 发起流式请求，由 FastAPI 主导助手运行。

## 后端 LLM 层

应当引入 PydanticAI 作为后端答案生成的编排层。它用类型化的 agent 边界取代临时的提示词调用。

推荐的后端模块：

```text
backend/app/
├── api/
│   ├── auth.py                 # 注册、登录、刷新、登出路由
│   ├── chat.py                 # 聊天线程与流式的 FastAPI 路由
│   └── documents.py            # 文档与分块的只读查询路由（绝不触发摄入）
├── core/
│   ├── config.py               # settings 单例，环境变量的唯一来源
│   └── embeddings.py           # 嵌入客户端，离线入库与线上检索共用同一份
├── auth/
│   ├── dependencies.py         # get_current_user 依赖
│   ├── jwt.py                  # JWT 签发与校验
│   ├── password.py             # 密码哈希
│   └── service.py              # 注册/登录业务逻辑
├── chat/
│   ├── orchestrator.py         # 端到端协调一轮对话
│   ├── messages.py             # AI SDK 消息与内部消息类型的双向转换
│   └── streaming.py            # 发出兼容 AI SDK 的流式事件
├── assistant/
│   ├── agent.py                # PydanticAI agent 定义
│   ├── deps.py                 # agent 的运行时依赖 dataclass
│   └── outputs.py              # GroundedAnswer、Citation、SourcePassage
├── retrieval/
│   ├── queries.py              # pgvector 与全文检索 SQL 查询
│   ├── fusion.py               # 混合检索的倒数排名融合（RRF）
│   └── retriever.py            # 从查询到原文段落的检索逻辑（查询向量化用 core.embeddings）
├── grounding/
│   └── validator.py            # 确保引用能对应到检索到的段落
├── database/
│   ├── session.py              # SQLAlchemy Engine、连接池与 Session
│   ├── models.py               # 供 Alembic autogenerate 使用的 SQLAlchemy 表模型
│   ├── users.py                # 用户记录的持久化
│   ├── chats.py                # 会话、线程、消息与引用的持久化
│   └── documents.py            # 源文档、分块、嵌入与检索查询
└── config.py
```

`database/session.py` 负责数据库接入，它管理：

```text
SQLAlchemy Engine
      ↓
Connection Pool
      ↓
Session
      ↓
PostgreSQL
```

这些命名应体现产品工作流，而非一个泛化的 service 层。`chat/orchestrator.py` 负责完整的一轮对话生命周期，`assistant/agent.py` 负责 LLM 边界，`retrieval/` 负责混合的原文段落检索，`grounding/` 负责「答案必须引用检索到的证据」这一信任契约。

agent 应当接收显式依赖，而不是伸手去拿全局变量：

```python
@dataclass
class DocumentAgentDeps:
    user_id: str
    thread_id: str
    retriever: DocumentRetriever
    grounding_validator: GroundingValidator


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    cited_passages: list[SourcePassage]
```

agent 的指令中应写入产品契约：

- 只依据检索到的段落作答。
- 每条事实性陈述都要给出引用。
- 如果检索到的上下文不充分，就明确说明语料中没有足够的证据。
- 不提供股票推荐或投资建议。
- 答案要简洁到便于分析师快速审阅，同时包含足够多被引用的段落以便验证答案。

检索与事实依据校验保持独立于 PydanticAI。这样摄入、检索测试和引用校验都可以在不调用 LLM 的情况下进行测试。

## 检索策略

Document Copilot 使用混合检索。

检索链路：

```text
OpenRouter 嵌入（查询向量化）
        ↓
PostgreSQL + pgvector
        ↓
semantic search
```

步骤：

1. 用配置好的嵌入模型（经 OpenRouter）对用户查询做向量化。
2. 用 `pgvector` 对 `document_chunks.embedding` 做语义检索。
3. 用 Postgres 全文检索对 `document_chunks.search_vector` 做字面量检索。
4. 在 Python 中用倒数排名融合（Reciprocal Rank Fusion）合并两个排序列表。
5. 取回选中的分块、源文档元数据，以及可选的相邻分块，用于事实依据校验。

语义检索 SQL：

```sql
SELECT
    id,
    content,
    1 - (embedding <=> :query_embedding) AS similarity
FROM document_chunks
WHERE document_id = :document_id
ORDER BY embedding <=> :query_embedding
LIMIT 5;
```

HNSW 索引也一样：

```sql
CREATE INDEX document_chunks_embedding_idx
ON document_chunks
USING hnsw (embedding vector_cosine_ops);
```

混合检索的整体形态保持不变：

```text
用户问题
   │
   ├──→ Vector Search
   │
   └──→ Full Text Search
            │
            ↓
          RRF
            ↓
        Top-K chunks
            ↓
           LLM
```

这样让数据库负责高效的排序检索，让应用层负责产品特有的排序策略。首个实现应避免由 agent 生成 SQL；PydanticAI agent 接收的是有边界的工具，例如 `search_filings`、`read_chunk` 和 `read_surrounding_chunks`。

## 数据模型

PostgreSQL 的表应当小而面向产品：

```text
PostgreSQL
 ├── users
 ├── chat_threads
 ├── chat_messages
 ├── source_documents
 ├── document_chunks
 ├── message_citations
 └── pgvector
```

- `users`：用户账号记录，包含邮箱与密码哈希。
- `chat_threads`：线程元数据、所有者、标题、时间戳。
- `chat_messages`：按顺序排列的用户与助手消息，在有用时保存兼容 AI SDK 的消息 JSON。
- `message_citations`：关联到助手消息的规范化引用记录。
- `source_documents`：原始文档记录，包含披露文件元数据、来源 URL 和规范化后的 Markdown 内容。
- `document_chunks`：分块文本、分块元数据、嵌入向量，以及生成的全文检索向量。

`source_documents` 保存每份披露文件规范化后的 Markdown 版本，这样应用可以重新分块、检视和引用原始抽取文本，而无需回过头去翻下载下来的 HTML 文件。`document_chunks` 保存可直接检索的段落：

- 分块 ID
- 文档 ID
- 分块序号
- 页码或章节元数据
- 分块文本
- 嵌入向量
- 生成的 `tsvector`，用于全文检索
- token 数量
- 元数据 JSON：股票代码、公司、披露文件类型、申报日期、年份、 accession number、页码、章节和源偏移

混合检索对 `document_chunks` 执行两个有边界的查询：一个语义 `pgvector` 查询和一个 Postgres 全文查询。后端用倒数排名融合（RRF）合并这两个排序列表，然后取回选中的分块及相邻上下文用于事实依据校验。

## Schema 管理

数据库 schema 变更由后端通过 SQLAlchemy 模型和 Alembic 迁移管理：

```text
SQLAlchemy
      ↓
Alembic
      ↓
PostgreSQL
```

工作流是：

1. 更新 `app/database/models.py` 中的 SQLAlchemy 模型。
2. 用 `uv run alembic revision --autogenerate -m "<change>"` 生成候选迁移。
3. 审阅 `backend/alembic/versions/` 中生成的迁移文件。
4. 对 autogenerate 无法可靠推断的 Postgres 特性，显式补充迁移操作。
5. 执行 `uv run alembic upgrade head`。
6. 同时提交模型变更和迁移文件。

普通的表和普通索引应尽量体现在 SQLAlchemy 模型中。以下内容应在迁移里用 `op.execute()` 显式书写，或通过仔细审阅的 Alembic 操作完成：

- `create extension if not exists vector`
- `vector(1024)` 嵌入列（如果 SQLAlchemy 的类型渲染不够用；宽度须低于 pgvector 索引的 2000 维上限）
- 生成的 `tsvector` 列
- 用于向量检索的 HNSW 索引
- 用于全文检索和 JSON 元数据的 GIN 索引

行级数据隔离由应用层保证：所有按用户隔离的查询都显式按 `user_id` 过滤。

Alembic 使用数据库的直连连接串执行迁移。

## 事实依据与引用策略

事实依据是架构的一部分，而不只是提示词偏好。

后端应强制执行以下不变式：

- 每条助手答案至少有一条引用，除非答案明确说明证据不足。
- 每条引用都必须对应一个检索到的原文段落。
- 被引用的段落要带足够元数据，让前端能展示公司、披露文件、日期、页码或章节以及摘录。
- 模型不能引用本次请求未检索到的文档。
- 如果引用校验失败，后端返回一个受控的失败响应，而不是一个措辞漂亮但无依据的答案。

该策略应由后端围绕检索、引用抽取和事实依据强制执行的单元测试来覆盖。

## 错误处理

预期的错误类别：

- `401 Unauthorized`：JWT 缺失、过期或无效。
- `403 Forbidden`：已认证用户试图访问他人线程。
- `404 Not Found`：线程或源文档不存在。
- `422 Unprocessable Entity`：请求负载非法。
- `502 Bad Gateway`：上游 LLM 故障。
- `500 Internal Server Error`：后端意外故障。

前端应渲染友好提示，同时在日志中保留足够的技术细节以便排查。在共享 API 客户端中，网络与 CORS 失败应当能与 HTTP 失败区分开。收到 `401` 时，前端应尝试用 refresh token 换新 access token，失败则跳转登录。

## 配置

每个服务必须保留一个 settings 模块作为事实来源。

前端设置：

- `VITE_API_BASE_URL`

后端设置：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/document_copilot

JWT_SECRET_KEY=
JWT_ALGORITHM=HS256

OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

EMBEDDING_MODEL=baai/bge-m3
EMBEDDING_DIMENSIONS=1024
```

这样整个系统的依赖关系非常干净：

```text
FastAPI
 │
 ├── PostgreSQL
 ├── pgvector
 └── OpenRouter
```

不要在组件、路由处理函数或 service 中直接读取环境变量。前端代码使用 `src/lib/env.ts`，后端代码使用 `app/core/config.py`。

## 部署形态

部署形态：

```text
Railway / 云服务器
├── Frontend
├── Backend
└── PostgreSQL
      └── pgvector
```

Railway 上运行前端（静态 Vite 构建物）与后端（Uvicorn 的 FastAPI 服务），PostgreSQL（含 pgvector 扩展）以托管数据库或 Railway 数据库形态部署。原始下载文件仍是 gitignore 掉的本地摄入输入，除非后续工作流把它们存进对象存储。

开发环境使用 Docker Compose：

```text
Docker Compose
├── frontend
├── backend
└── postgres
      └── pgvector
```

这带来一个额外的好处：我们会完整经历 Docker、PostgreSQL、数据库连接池、Alembic、pgvector、HNSW、网络和环境变量的搭建与调优。

## 实施顺序

按以下顺序实施，**不要一开始同时改数据库、Auth、前端、RAG**：

```text
① PostgreSQL + pgvector
        ↓
② SQLAlchemy + Alembic
        ↓
③ 数据库访问层（session.py + 仓储模块）
        ↓
④ JWT Auth
        ↓
⑤ 前端 auth 模块
        ↓
⑥ RAG + pgvector
        ↓
⑦ Full Text Search
        ↓
⑧ RRF
        ↓
⑨ PydanticAI
        ↓
⑩ Grounding + Citation
```

展开为具体工作项：

1. 起一个带 pgvector 扩展的 PostgreSQL 实例（Docker Compose 或托管数据库）。
2. 配置 SQLAlchemy（asyncpg）与 Alembic，建立 `database/session.py`。
3. 建初始迁移：`users`、`chat_threads`、`chat_messages`、`source_documents`、`document_chunks`、`message_citations`，以及 pgvector/HNSW/GIN 相关显式操作。
4. 实现 `database/users.py`、`database/chats.py`、`database/documents.py` 数据访问层。
5. 实现 `auth/`（jwt、password、service、dependencies）与 `/auth/*` 路由。
6. 前端加入 `src/auth/` 模块与 token 注入。
7. 加入 pgvector 语义检索。
8. 加入 Postgres 全文检索。
9. 加入 RRF 融合。
10. 接入 PydanticAI agent。
11. 接入 Grounding 与 Citation 校验。
12. 完善引用、原文段落、空状态和错误的最终 UI。

## 非目标

- 不使用 Next.js、SSR、服务端组件或前端 route handler。
- 不从浏览器直接调用 OpenRouter。
- 不引入独立的托管向量数据库——pgvector 承载全部向量检索。
- 不使用任何 BaaS 身份服务，认证完全由 FastAPI 实现。
- 不做多租户架构。
- 不接入外部行情/新闻数据。
- 不做交易推荐或生成股票推荐。
