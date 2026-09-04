# 后端 — 智能体说明

这是 Document Copilot 的 FastAPI 服务。请先阅读 [../AGENTS.md](../AGENTS.md) —— 通用开发规范在那里。本文件补充后端特有的约定。

## 技术栈

- Python 3.12+
- FastAPI + uvicorn
- Pydantic v2 + pydantic-settings
- 出站 HTTP 使用 `httpx`
- 测试使用 `pytest`
- SQLAlchemy（`asyncpg` 驱动）+ Alembic 迁移，用于数据库访问与 schema 变更
- OpenAI SDK 用于 LLM 与 embeddings，统一通过 OpenRouter 网关调用（`base_url=https://openrouter.ai/api/v1`）
- `pyjwt` 用于 JWT 签发/校验，`bcrypt` 直接用于密码哈希（passlib 已停止维护且与 bcrypt 5.0 不兼容，勿重新引入）
- `pgvector` 用于语义检索，Postgres 全文检索用于关键词检索。混合检索应分别执行向量查询与全文查询，再用 Reciprocal Rank Fusion（RRF）在 Python 中融合排序结果。
- `structlog` 用于日志
- `uv` 用于依赖与项目管理

## 依赖策略

通用策略见 [../AGENTS.md](../AGENTS.md)。后端补充：

- **优先使用标准库：** `pathlib`、`datetime`、`uuid`、`enum`、`dataclasses`、`asyncio`、`collections`、`itertools`、`json`、`urllib`。
- **未经说明不得引入：** `python-dateutil`、`toolz`、`funcy`、`more-itertools`、各类小型 JSON/字符串微库，以及封装在已声明 SDK 之上的「更好用的」包装层。
- 开发依赖（测试/lint/构建）标准可放宽，但仍应选择使用广泛、体量轻的工具（`pytest`、`ruff`、`httpx`）。

## 目录结构（在构建过程中创建）

```text
backend/
├── alembic/
│   ├── env.py           # 导入 app 的数据库 metadata，供 autogenerate 使用
│   └── versions/        # 经过评审的迁移文件
├── alembic.ini
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── config.py        # Pydantic settings —— 环境变量的唯一来源
│   ├── api/             # FastAPI 路由：auth.py、chat.py、documents.py
│   ├── auth/            # JWT 签发/校验、密码哈希、当前用户依赖项
│   ├── chat/            # 对话轮次编排、AI SDK 消息转换、流式输出
│   ├── assistant/       # PydanticAI agent、deps、outputs、instructions
│   ├── retrieval/       # pgvector/全文查询、RRF 融合、原文段落查找
│   ├── grounding/       # 引用校验与答案有据性检查
│   ├── database/        # session.py（engine/pool/session）、模型、带类型的查询辅助函数
│   └── prompts/         # prompt / 指令模板（若未与 assistant 放在一起）
├── ingest/              # 一次性数据入库脚本（Markdown 抽取、分块、向量化、写入 PostgreSQL）
├── tests/
└── pyproject.toml
```

## 代码风格（后端特有）

- **公开函数与模块级对象要写类型标注。** 不必给每个局部变量都加注解。
- **请求链路上的代码默认使用 async。** 不要在事件循环中执行阻塞式 I/O。使用临时文件与少量同步文件读取是可以的（速度很快）；网络调用必须是异步的。
- **所有路由处理函数以及任何涉及 I/O 的服务函数都使用 `async def`。**
- **仅在边界处做校验。** HTTP 输入由 Pydantic 模型校验；外部 API 响应在解析时校验；内部调用方视为可信。

## 配置

- `app.core.config.settings` 是唯一来源。在需要的地方导入 settings；应用代码中绝不调用 `os.getenv`，绝不调用 `load_dotenv`。
- 如果第三方 SDK 直接读取 `os.environ`，就在 `app/core/config.py` 中做镜像配置 —— 不要在别处到处写 `setdefault`。
- 启动时若必需的环境变量缺失，应快速失败（fail fast）。

## 数据库迁移

- Alembic 是 schema 变更的唯一来源。绝不在迁移之外手工修改数据库表。
- SQLAlchemy 模型描述普通的表与列。Alembic autogenerate 生成候选迁移，但每个生成的迁移在应用前都必须经过评审。
- Postgres 特有功能应写成显式的迁移操作：`create extension vector`、`vector(N)` 向量列、生成的 `tsvector` 列，以及 HNSW/GIN 索引。
- 行级隔离在应用层实现：所有面向用户的查询都要按 `user_id` 过滤。不使用 RLS。
- 在 `backend/` 目录下执行 `uv run alembic upgrade head` 运行迁移。

## 测试

- **优先单元测试而非集成测试。** 在服务边界处做 mock。
- 快速测试套件（`pytest -m "not integration"`）必须保持通过，且不得访问网络 / 数据库。
- 集成测试使用 `@pytest.mark.integration` 标记，可能需要真实 PostgreSQL 数据库或真实 OpenRouter 凭据。
- **改动嵌入/向量链路后、以及对全量语料入库前，先跑 `uv run python -m ingest.smoke`。** 它用真实 OpenRouter 凭据把一份文档的 `DEFAULT_CHUNK_COUNT` 个 chunk 走完 抽取 → 分块 → embed → 写 pgvector → 回读最近邻 → 删除，花费不到 0.0001 美元。它专门抓那些「全量跑到一半才暴露、而钱已经烧掉」的错误：API Key 失效、模型忽略 `dimensions`、返回维度与列宽不符、chunker 元数据键缺失。
- 真调 API 的测试必须用 `skipif` 跳过缺 key 的情况（`tests/ingest/test_smoke.py` 是范例）—— 没有凭据的环境跑 `pytest -m integration` 不得变红。
- 改 `settings.embedding_dimensions` 或更换嵌入模型后，`tests/ingest/test_schema.py` 负责比对配置 / ORM 模型 / 数据库实际列宽是否一致；迁移 `29baa7ace0d1` 的 `_WIDTH_AFTER` 需同步修改。
- 测试文件与其测试对象放在一起（`retrieval/retriever.py` → `tests/retrieval/test_retriever.py`）。
- 必须覆盖的测试：入库逻辑、检索、引用抽取、有据性校验（grounding enforcement）。

## 反模式（禁止）

- 在模块中使用 `os.getenv` / `load_dotenv`。
- 用自定义 envelope 类包裹 FastAPI 响应。
- 过度捕获 `Exception` 只为打日志再抛出 —— 让它直接向上抛出。
- 通过全局变量共享状态，而不用 FastAPI 的 `app.state` 或依赖注入。
- 用静默的兜底逻辑掩盖真实的配置错误。
- 在单元测试中 mock LLM 却不测试 grounding 契约 —— prompt 就是产品本身。
- 没跑 `ingest.smoke` 就对全量语料开跑向量化 —— 一次调用不到 1 厘钱，能省下整批重跑的费用。
- 为省 API 费用把 `ingest/smoke.py` 的 `DEFAULT_CHUNK_COUNT` 降到 1 —— 单行时「离 X 最近的向量是 X」构造性为真，最近邻断言就废了。
- 在迁移里 import 应用代码（包括 `settings`）—— 迁移是历史快照，import 会让它的语义随当前配置漂移。宽度一类需要与应用对齐的值写成具名常量 + 注释，由测试兜底。
