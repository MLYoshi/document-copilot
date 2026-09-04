import json
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.password import hash_password
from app.core.config import settings
from app.core.embeddings import EmbedFn, get_embedding
from app.database.models import DocumentChunk, DocumentStatus, SourceDocument, User
from app.database.session import session_factory as default_session_factory
from ingest.chunker import chunk_markdown
from ingest.extractor import extract_markdown

logger = structlog.get_logger()


@dataclass
class IngestStats:
    processed: int = 0
    skipped: int = 0
    failed: int = 0


async def seed_corpus_owner(session: AsyncSession) -> User:
    result = await session.execute(
        select(User).where(User.email == settings.corpus_owner_email)
    )
    user = result.scalar_one_or_none()
    if user is None:
        # random unusable password: the account exists only to own corpus rows
        user = User(
            email=settings.corpus_owner_email,
            password_hash=await hash_password(secrets.token_urlsafe(32)),
        )
        session.add(user)
        await session.commit()
    return user


async def _find_document(
    session: AsyncSession, user_id: uuid.UUID, accession: str
) -> SourceDocument | None:
    result = await session.execute(
        select(SourceDocument).where(
            SourceDocument.user_id == user_id,
            SourceDocument.metadata_json["accession_number"].astext == accession,
        )
    )
    return result.scalar_one_or_none()


def _document_fields(filing: dict[str, str]) -> dict:
    """Manifest-derived columns, shared by the create and rebuild paths."""
    return {
        "title": f"{filing['ticker']} {filing['form']} ({filing['filing_date']})",
        "source_url": filing.get("source_url"),
        "metadata_json": {
            key: filing[key]
            for key in (
                "ticker",
                "cik",
                "form",
                "filing_date",
                "report_date",
                "accession_number",
                "primary_document",
            )
        },
    }


async def _ingest_filing(
    session: AsyncSession,
    user_id: uuid.UUID,
    filing: dict[str, str],
    downloads_dir: Path,
    embed: EmbedFn,
) -> Literal["processed", "skipped"]:
    accession = filing["accession_number"]
    existing = await _find_document(session, user_id, accession)
    if existing is not None and existing.status == DocumentStatus.completed:
        return "skipped"

    html = (downloads_dir / filing["local_path"]).read_text(encoding="utf-8")
    markdown = extract_markdown(html)
    chunks = chunk_markdown(markdown)
    if not chunks:
        raise ValueError(f"no content extracted from {filing['local_path']}")

    fields = _document_fields(filing)
    if existing is not None:
        document = existing
        for key, value in fields.items():
            setattr(document, key, value)
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
    else:
        document = SourceDocument(user_id=user_id, content=markdown, **fields)
        session.add(document)

    # pending/failed -> processing, so a crash mid-run is visible as an
    # incomplete document that the next run will rebuild
    document.content = markdown
    document.status = DocumentStatus.processing
    await session.commit()

    embeddings = await embed([chunk.content for chunk in chunks])

    for chunk, vector in zip(chunks, embeddings, strict=True):
        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.metadata["token_count"],
                metadata_json=dict(chunk.metadata),
                embedding=vector,
            )
        )
    document.status = DocumentStatus.completed
    await session.commit()
    return "processed"


async def _mark_failed(
    session: AsyncSession, user_id: uuid.UUID, filing: dict[str, str]
) -> None:
    accession = filing.get("accession_number")
    if not accession:
        return
    document = await _find_document(session, user_id, accession)
    if document is not None and document.status != DocumentStatus.completed:
        document.status = DocumentStatus.failed
        await session.commit()


async def ingest_corpus(
    downloads_dir: Path,
    *,
    session_factory: async_sessionmaker | None = None,
    embed: EmbedFn | None = None,
) -> IngestStats:
    """Ingest every filing listed in ``downloads_dir/manifest.json``.

    Re-running is idempotent: filings whose document is already ``completed``
    are skipped; documents in any other state are rebuilt from scratch.
    Dedup is check-then-insert, so runs must not be concurrent (single-process
    assumption for a one-shot script).
    """
    manifest = json.loads((downloads_dir / "manifest.json").read_text(encoding="utf-8"))
    session_factory = session_factory or default_session_factory
    embed = embed or get_embedding
    stats = IngestStats()

    async with session_factory() as session:
        user = await seed_corpus_owner(session)
        # capture the id up front: rollback() below expires ORM objects, and
        # touching user.id afterwards would trigger a sync lazy refresh
        user_id = user.id
        for filing in manifest["filings"]:
            try:
                outcome = await _ingest_filing(session, user_id, filing, downloads_dir, embed)
            except Exception:
                await session.rollback()
                logger.exception(
                    "ingest_filing_failed", accession=filing.get("accession_number")
                )
                await _mark_failed(session, user_id, filing)
                stats.failed += 1
                continue
            if outcome == "skipped":
                stats.skipped += 1
            else:
                stats.processed += 1
    return stats
