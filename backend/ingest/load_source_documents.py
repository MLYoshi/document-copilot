"""Load markdown bodies and table artifacts into source_documents + document_tables.

Stage 4 of the offline pipeline: reads ``manifest.json`` plus the artifacts
written by data/convert_to_markdown.py (``data/markdown/*.md``) and
ingest.section_tables (``data/tables/*.json``), and writes one
``source_documents`` row per filing with its ``document_tables`` rows.
Prose chunks keep referencing tables through the ``[Table N: caption]``
placeholders, whose N matches ``document_tables.table_index``.

Run: uv run python -m ingest.load_source_documents [downloads_dir]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import DocumentStatus, DocumentTable, SourceDocument
from app.database.session import session_factory as default_session_factory
from ingest.pipeline import _document_fields, _find_document, seed_corpus_owner

logger = structlog.get_logger()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOWNLOADS_DIR = ROOT / "data" / "downloads"
DEFAULT_MARKDOWN_DIR = ROOT / "data" / "markdown"
DEFAULT_TABLES_DIR = ROOT / "data" / "tables"


@dataclass
class LoadStats:
    processed: int = 0
    skipped: int = 0
    failed: int = 0


def _markdown_path(markdown_dir: Path, filing: dict[str, str]) -> Path:
    return markdown_dir / Path(filing["local_path"]).with_suffix(".md")


def _tables_path(tables_dir: Path, filing: dict[str, str]) -> Path:
    return tables_dir / Path(filing["local_path"]).with_suffix(".json")


def _load_tables(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _placeholder_indices(markdown: str) -> set[int]:
    """Table numbers referenced by placeholders in the markdown body."""
    return {int(m) for m in re.findall(r"\[Table (\d+)(?::|\])", markdown)}


async def _load_filing(
    session: AsyncSession,
    user_id,
    filing: dict[str, str],
    markdown_dir: Path,
    tables_dir: Path,
) -> str:
    accession = filing["accession_number"]
    existing = await _find_document(session, user_id, accession)
    if existing is not None and existing.status == DocumentStatus.completed:
        return "skipped"

    md_path = _markdown_path(markdown_dir, filing)
    markdown = md_path.read_text(encoding="utf-8")
    tables = _load_tables(_tables_path(tables_dir, filing))

    # every placeholder must have a stored table, otherwise section_path
    # linking downstream would hit gaps
    indices = _placeholder_indices(markdown)
    stored = {t["table_index"] for t in tables}
    missing = indices - stored
    if missing:
        raise ValueError(f"{md_path.name}: placeholders without tables: {sorted(missing)}")

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
    await session.execute(
        delete(DocumentTable).where(DocumentTable.document_id == document.id)
    )
    for table in tables:
        session.add(
            DocumentTable(
                document_id=document.id,
                table_index=table["table_index"],
                caption=table.get("caption") or None,
                section_path=table.get("section_path") or None,
                markdown=table["markdown"],
                rows=table["rows"],
            )
        )
    await session.commit()
    return "processed"


async def load_corpus(
    downloads_dir: Path,
    markdown_dir: Path = DEFAULT_MARKDOWN_DIR,
    tables_dir: Path = DEFAULT_TABLES_DIR,
    *,
    session_factory: async_sessionmaker | None = None,
) -> LoadStats:
    """Load every filing in ``downloads_dir/manifest.json`` from artifacts.

    Re-running is idempotent: filings already ``completed`` are skipped;
    documents in any other state have their tables deleted and rebuilt.
    """
    manifest = json.loads((downloads_dir / "manifest.json").read_text(encoding="utf-8"))
    session_factory = session_factory or default_session_factory
    stats = LoadStats()

    async with session_factory() as session:
        user = await seed_corpus_owner(session)
        user_id = user.id
        for filing in manifest["filings"]:
            try:
                outcome = await _load_filing(
                    session, user_id, filing, markdown_dir, tables_dir
                )
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
