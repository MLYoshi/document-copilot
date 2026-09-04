# 后端配置

本项目使用独立的 Python + FastAPI 后端，因为服务端要承担的是 AI 与文档处理工作，而不仅仅是基础的 Web 增删改查。Python 在摄入、切分、嵌入、检索、评估和 LLM 编排这些环节上拥有最成熟的生态。把这些逻辑放在一个专门的 API 之后，前端就能专注于用户体验，而由后端统一负责数据访问、流程编排和答案溯源。

## 初始化（从空的 `backend/` 开始）

```bash
cd backend
uv sync
uv add fastapi uvicorn pydantic pydantic-settings httpx structlog openai pydantic-ai sqlalchemy alembic asyncpg pgvector pyjwt "passlib[bcrypt]"
uv add --dev pytest ruff
```

## PostgreSQL + pgvector（Docker Compose）

后端需要一个装了 `pgvector` 扩展的 PostgreSQL 实例。本地用 Docker Compose 启动即可 —— `backend/compose.yml`：

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: document_copilot
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d document_copilot"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

启动并确认扩展可用：

```bash
cd backend
docker compose up -d postgres
docker compose exec postgres psql -U postgres -d document_copilot -c "create extension if not exists vector;"
```

让后端指向该实例（见 `backend/.env.example`）：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/document_copilot
```

`asyncpg` 是 SQLAlchemy 使用的异步驱动。任何允许安装 `vector` 扩展的托管 PostgreSQL 用法完全相同 —— 只有 `DATABASE_URL` 需要改。第一个 Alembic 迁移会执行 `create extension if not exists vector`，所以上面的命令只是一次快速的自检。

## 数据库迁移

本项目的数据库结构变更由 Alembic 负责。SQLAlchemy 模型描述应用表结构，Alembic 迁移负责把这些变更应用到 PostgreSQL。

在 `backend/` 下初始化一次 Alembic：

```bash
uv run alembic init alembic
```

配置 `alembic/env.py`，让它导入应用的 SQLAlchemy metadata，并从 `app.config.settings` 读取 `DATABASE_URL`。迁移直接连接数据库执行 —— 前面不经过任何连接池中间件。

修改 SQLAlchemy 模型后生成迁移：

```bash
uv run alembic revision --autogenerate -m "add document tables"
```

务必人工审查生成的迁移。对于 autogenerate 无法可靠推断的 Postgres 特性，需要显式补上相应操作：

- `create extension if not exists vector`
- `vector(2048)` 列（宽度由 `settings.embedding_dimensions` 决定）
- 生成列 `tsvector`
- HNSW 与 GIN 索引

行级隔离在应用层通过按 `user_id` 过滤实现 —— 没有需要迁移的 RLS 策略。

应用迁移：

```bash
uv run alembic upgrade head
```

## 运行

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## 导入（`from app...`）

`uv sync` 会把 `backend/app` 以可编辑包的形式安装，因此在使用该后端虚拟环境的 uvicorn、直接执行 Python、测试以及 Jupyter kernel 中，`from app...` 形式的导入都能正常工作。

`backend/pyproject.toml` 中的 `[build-system]` 和 `[tool.hatch.build.targets.wheel]` 段落告诉 uv 如何安装本地的 `app/` 包。如果缺少这个包安装，导入就会依赖于当前工作目录或手动配置的 `PYTHONPATH`，在 notebook 和 IDE 的运行按钮里非常脆弱。

推荐的 API 服务启动命令：

```bash
cd backend
uv run uvicorn app.main:app --reload
```

直接执行文件同样可行：

```bash
cd backend
uv run python app/main.py
```

在 Jupyter 中，安装并选择后端 kernel：

```bash
cd backend
uv run python -m ipykernel install --user --name document-copilot-backend --display-name "Document Copilot Backend"
```

之后 notebook 即可导入后端模块：

```python
from app.config import settings
```

## 示例 SEC 数据

在仓库根目录执行（纯标准库脚本，不需要后端环境）：

```bash
uv run data/download.py
```
