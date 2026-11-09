from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.embeddings import EmbedFn, get_embedding
from app.core.summarizer import SummarizeFn, get_summary
from app.database.models import DocumentStatus, SourceDocument
from app.database.session import session_factory as default_session_factory

logger = structlog.get_logger()


async def _embed_document(
    session: AsyncSession,
    document: SourceDocument,
    embed: EmbedFn,
    summarize: SummarizeFn,
) -> str:
    if not document.content.strip():
        raise ValueError(f"no content available for document {document.id}")

    summary = await summarize(document.content)
    (summary_vector,) = await embed([summary])

    document.summary = summary
    document.summary_embedding = summary_vector
    await session.commit()
    return "processed"


async def embed_corpus(
    *,
    session_factory: async_sessionmaker | None = None,
    embed: EmbedFn | None = None,
    summarize: SummarizeFn | None = None,
) -> dict[str, int]:
    session_factory = session_factory or default_session_factory
    embed = embed or get_embedding
    summarize = summarize or get_summary

    stats = {"processed": 0, "skipped": 0, "failed": 0}
    async with session_factory() as session:
        result = await session.execute(
            select(SourceDocument).where(
                SourceDocument.status == DocumentStatus.completed,
                SourceDocument.deleted_at.is_(None),
                SourceDocument.summary_embedding.is_(None),
            )
        )
        documents = result.scalars().all()
        for document in documents:
            try:
                await _embed_document(session, document, embed, summarize)
            except Exception:
                await session.rollback()
                logger.exception("embed_document_failed", document_id=str(document.id))
                stats["failed"] += 1
                continue
            stats["processed"] += 1
    return stats


async def main() -> int:
    print("Summarizing and embedding corpus ...")
    stats = await embed_corpus()
    print(
        f"Done: {stats['processed']} processed, {stats['skipped']} skipped, "
        f"{stats['failed']} failed"
    )
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
