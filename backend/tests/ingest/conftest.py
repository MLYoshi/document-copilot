import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from tests.conftest import TEST_DB_NAME, test_database_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"


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
    """Deterministic offline embedder; can be told to fail on a marker string."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.fail_on: str | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        if self.fail_on is not None and any(self.fail_on in t for t in texts):
            raise RuntimeError("embedding service unavailable")
        return [[(len(t) % 7 + 1) * 0.01] * 1536 for t in texts]


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


APPLE_HTML = (FIXTURES / "mini_10k.html").read_text(encoding="utf-8")

NVDA_HTML = """\
<!DOCTYPE html>
<html>
<head><title>nvda-20250126.htm</title></head>
<body>
  <h2>Item 1. Business</h2>
  <p>NVIDIA pioneered accelerated computing to solve the most challenging computational problems.</p>
  <h3>Data Center</h3>
  <p>Data Center revenue for fiscal year 2025 grew, driven by demand for large language models.</p>
</body>
</html>
"""

FILINGS = [
    {
        "ticker": "AAPL",
        "cik": "0000320193",
        "form": "10-K",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "accession_number": "0000320193-24-000123",
        "primary_document": "aapl-20240928.htm",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019324000123/aapl-20240928.htm"
        ),
        "local_path": "2024/aapl_10k.html",
    },
    {
        "ticker": "NVDA",
        "cik": "0001045810",
        "form": "10-K",
        "filing_date": "2025-02-26",
        "report_date": "2025-01-26",
        "accession_number": "0001045810-25-000023",
        "primary_document": "nvda-20250126.htm",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/1045810/"
            "000104581025000023/nvda-20250126.htm"
        ),
        "local_path": "2025/nvda_10k.html",
    },
]


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    (tmp_path / "2024").mkdir()
    (tmp_path / "2024" / "aapl_10k.html").write_text(APPLE_HTML, encoding="utf-8")
    (tmp_path / "2025").mkdir()
    (tmp_path / "2025" / "nvda_10k.html").write_text(NVDA_HTML, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"filings": FILINGS}), encoding="utf-8"
    )
    return tmp_path
