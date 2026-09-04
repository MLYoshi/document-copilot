"""Root test conftest.

Integration tests run against a dedicated database (document_copilot_test).
The DATABASE_URL override must happen here: this conftest is imported by
pytest at startup, before any test module imports app.core.config — whose cached
settings singleton would otherwise leak the development URL into alembic
migration runs when the full suite executes.
"""

import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "document_copilot_test"


def _switch_database(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", parts.query, ""))


def _base_database_url() -> str | None:
    # parsed manually: pydantic-settings' env_file would only be read by
    # app.core.config at import time, which is exactly what we must precede
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        env_file = BACKEND_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip("'\"")
                    break
    return url or None


def test_database_url() -> str:
    base = _base_database_url()
    if base is None:
        raise RuntimeError(
            "DATABASE_URL not found: integration tests need backend/.env "
            "or the DATABASE_URL environment variable"
        )
    return _switch_database(base, TEST_DB_NAME)


# Only override when a base URL exists; without one, app.core.config fails on its
# own and the fast test suite must not break at collection time.
_base = _base_database_url()
if _base:
    os.environ["DATABASE_URL"] = _switch_database(_base, TEST_DB_NAME)


# --- Shared integration-test DB fixtures -------------------------------------
# Defined here so every test directory (ingest, retrieval, chat, ...) reuses
# them instead of re-declaring per-package copies. Fixtures are lazily
# evaluated: the fast suite never triggers a database creation or migration.


async def _create_test_database(url: str) -> None:
    parts = urlsplit(url)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, ""))
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = (
                await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": TEST_DB_NAME},
                )
            ).scalar()
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Create the dedicated test database and apply all migrations once."""
    url = test_database_url()
    asyncio.run(_create_test_database(url))
    cfg = Config(BACKEND_DIR / "alembic.ini")
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
async def db_engine(migrated_database):
    import app.database.models  # noqa: F401 — register tables on Base.metadata
    from app.database.base import Base

    engine = create_async_engine(test_database_url())
    async with engine.begin() as conn:
        tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


class FakeEmbedder:
    """Callable stand-in for ``get_embedding``; can fail on a marker string."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.fail_on: str | None = None

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        if self.fail_on is not None and any(self.fail_on in t for t in texts):
            raise RuntimeError("embedding service unavailable")
        return [[(len(t) % 7 + 1) * 0.01] * 1024 for t in texts]


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()
