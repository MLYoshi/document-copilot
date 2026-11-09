import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from supabase_auth.types import User

from app.auth.supabase import get_supabase_admin_client
from app.core.config import settings
from app.core.embeddings import EmbedFn, get_embedding
from app.core.summarizer import SummarizeFn, get_summary
from app.database.models import DocumentStatus, SourceDocument
from app.database.session import session_factory as default_session_factory
from ingest.extractor import extract_markdown

logger = structlog.get_logger()


@dataclass
class IngestStats:
    processed: int = 0
    skipped: int = 0
    failed: int = 0


async def seed_corpus_owner(session: AsyncSession) -> User:
    """Resolve or create the corpus owner in Supabase Auth."""
    admin = get_supabase_admin_client().auth.admin
    page = 1
    while True:
        users = await admin.list_users(page=page, per_page=1000)
        if user := next(
            (u for u in users if u.email == settings.corpus_owner_email), None
        ):
            return user
        if len(users) < 1000:
            break
        page += 1
    response = await admin.create_user(
        {"email": settings.corpus_owner_email, "email_confirm": True}
    )
    if response.user is None:
        raise RuntimeError("Supabase did not return the corpus owner")
    return response.user


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
    summarize: SummarizeFn,
) -> Literal["processed", "skipped"]:
    accession = filing["accession_number"]
    existing = await _find_document(session, user_id, accession)
    if existing is not None and existing.status == DocumentStatus.completed:
        return "skipped"

    html = (downloads_dir / filing["local_path"]).read_text(encoding="utf-8")
    markdown = extract_markdown(html)
    if not markdown.strip():
        raise ValueError(f"no content extracted from {filing['local_path']}")

    summary = await summarize(markdown)
    (summary_vector,) = await embed([summary])

    fields = _document_fields(filing)
    if existing is not None:
        document = existing
        for key, value in fields.items():
            setattr(document, key, value)
    else:
        document = SourceDocument(user_id=user_id, content=markdown, **fields)
        session.add(document)

    document.content = markdown
    document.summary = summary
    document.summary_embedding = summary_vector
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
    summarize: SummarizeFn | None = None,
    only: str | None = None,
) -> IngestStats:
    manifest = json.loads((downloads_dir / "manifest.json").read_text(encoding="utf-8"))
    filings = manifest["filings"]
    if only is not None:
        filings = [f for f in filings if f["local_path"] == only]
        if not filings:
            raise ValueError(
                f"manifest 中找不到 local_path 为 {only!r} 的文件"
            )
    session_factory = session_factory or default_session_factory
    embed = embed or get_embedding
    summarize = summarize or get_summary
    stats = IngestStats()

    async with session_factory() as session:
        user = await seed_corpus_owner(session)
        user_id = user.id
        for filing in filings:
            try:
                outcome = await _ingest_filing(
                    session, user_id, filing, downloads_dir, embed, summarize
                )
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
