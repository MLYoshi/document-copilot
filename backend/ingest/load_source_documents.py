from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import DocumentStatus, SourceDocument
from app.database.session import session_factory as default_session_factory
from ingest.pipeline import _document_fields, _find_document, seed_corpus_owner

logger = structlog.get_logger()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOWNLOADS_DIR = ROOT / "data" / "downloads"
DEFAULT_MARKDOWN_DIR = ROOT / "data" / "markdown"


@dataclass
class LoadStats:
    processed: int = 0
    skipped: int = 0
    failed: int = 0


def _markdown_path(markdown_dir: Path, filing: dict[str, str]) -> Path:
    return markdown_dir / Path(filing["local_path"]).with_suffix(".md")


async def _load_filing(
    session: AsyncSession,
    user_id,
    filing: dict[str, str],
    markdown_dir: Path,
) -> str:
    accession = filing["accession_number"]
    existing = await _find_document(session, user_id, accession)
    if existing is not None and existing.status == DocumentStatus.completed:
        return "skipped"

    markdown = _markdown_path(markdown_dir, filing).read_text(encoding="utf-8")

    fields = _document_fields(filing)
    if existing is not None:
        document = existing
        for key, value in fields.items():
            setattr(document, key, value)
    else:
        document = SourceDocument(user_id=user_id, content=markdown, **fields)
        session.add(document)
    document.content = markdown
    document.status = DocumentStatus.completed
    await session.commit()
    return "processed"


async def load_corpus(
    downloads_dir: Path,
    markdown_dir: Path = DEFAULT_MARKDOWN_DIR,
    *,
    session_factory: async_sessionmaker | None = None,
) -> LoadStats:
    manifest = json.loads((downloads_dir / "manifest.json").read_text(encoding="utf-8"))
    session_factory = session_factory or default_session_factory
    stats = LoadStats()

    async with session_factory() as session:
        user = await seed_corpus_owner(session)
        user_id = user.id
        for filing in manifest["filings"]:
            try:
                outcome = await _load_filing(session, user_id, filing, markdown_dir)
            except Exception:
                await session.rollback()
                logger.exception(
                    "load_filing_failed", accession=filing.get("accession_number")
                )
                stats.failed += 1
                continue
            if outcome == "skipped":
                stats.skipped += 1
            else:
                stats.processed += 1
    return stats


async def main() -> int:
    downloads_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOWNLOADS_DIR
    print(f"Loading corpus artifacts from {downloads_dir} ...")
    stats = await load_corpus(downloads_dir)
    print(
        f"Done: {stats.processed} processed, {stats.skipped} skipped, "
        f"{stats.failed} failed"
    )
    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
