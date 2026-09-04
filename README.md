# Document Copilot

An internal AI chatbot that lets analysts query a corpus of documents in plain English and get sourced, citable answers.

## The client

**Driftwood Capital** — fictional independent investment research firm. Their analysts spend half their week reading 10-Ks and 10-Qs before they can produce any original analysis. Document Copilot eats that intake work so they can skip straight to insight.

Full brief: [docs/client-brief.md](docs/client-brief.md)

## Stack

| Layer            | Choice                                                             |
| ---------------- | ------------------------------------------------------------------ |
| Backend          | Python + FastAPI                                                   |
| Frontend         | Vite + React SPA + TypeScript                                      |
| Database         | PostgreSQL + pgvector, self-managed (users, chats, documents, chunks) |
| Migrations       | SQLAlchemy models + Alembic                                        |
| Retrieval        | `pgvector` semantic search + Postgres full-text search              |
| Auth             | FastAPI JWT (email + password)                                     |
| Cache            | Redis (cache / session state)                                      |
| Hosting          | Railway (frontend + backend + PostgreSQL)                          |
| LLM + embeddings | OpenAI SDK via the OpenRouter gateway                              |

## Repo layout

```text
document-copilot/
├── AGENTS.md           # agent instructions (read first)
├── README.md           # this file
├── data/               # local corpus + download script (payloads gitignored)
├── docs/
│   ├── architecture.zh-CN.md # target architecture (source of truth)
│   └── client-brief.md       # the client one-pager
├── backend/            # FastAPI service
└── frontend/           # React SPA (Vite)
```

## Prerequisites

Install these before setting up `backend/` or `frontend/`:

| Tool | Version | Used for | Install |
| ---- | ------- | -------- | ------- |
| [Python](https://www.python.org/downloads/) | 3.12+ | Backend runtime | OS package manager or python.org |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | latest | Backend deps + `data/download.py` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org/) | 20+ (LTS) | Frontend toolchain | nodejs.org or `nvm install --lts` |
| [pnpm](https://pnpm.io/installation) | latest | Frontend package manager | `corepack enable && corepack prepare pnpm@latest --activate` |

You also need a PostgreSQL instance with the `pgvector` extension and an OpenRouter API key. Start with the [PostgreSQL + pgvector](docs/guides/backend-setup.zh-CN.md#postgresql--pgvector-docker-compose) section of the backend guide, then create an [OpenRouter API key](https://openrouter.ai/keys) when the LLM layer is wired up.

## Running locally

To be added during the build. Setup guides:

- [Backend](docs/guides/backend-setup.zh-CN.md) — includes PostgreSQL + pgvector setup (Docker Compose or managed)
- [Frontend](docs/guides/frontend-setup.md)

## Sample SEC data

Use the standalone downloader to fetch a small local 10-K sample from SEC EDGAR.
Edit the params at the top of `data/download.py`, especially `USER_AGENT`, then run:

```bash
uv run data/download.py
```

By default this downloads the latest 5 10-K filings for AAPL, MSFT, NVDA, AMZN, and GOOGL into year folders under `data/downloads/` and writes a `manifest.json`.
Downloaded files are gitignored; the `data/` folder itself stays in git for the script and notes.
