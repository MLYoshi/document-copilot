"""Root test conftest.

Integration tests run against a dedicated database (document_copilot_test).
The DATABASE_URL override must happen here: this conftest is imported by
pytest at startup, before any test module imports app.core.config — whose cached
settings singleton would otherwise leak the development URL into alembic
migration runs when the full suite executes.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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
