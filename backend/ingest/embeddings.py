"""Chunk and embed source_documents into document_chunks.

Final stage of the offline pipeline: reads each ``source_documents.content``
from the database, reuses the shared chunker and the OpenRouter embedding
client, and writes ``document_chunks`` rows. Retrieval still runs purely on
prose chunks — tables stay structured-only in ``document_tables``.

Run: uv run python -m ingest.embeddings
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.embeddings import EmbedFn, get_embedding
from app.database.models import DocumentChunk, DocumentStatus, SourceDocument
from app.database.session import session_factory as default_session_factory
from ingest.chunker import chunk_markdown

logger = structlog.get_logger()


async def _chunk_count(session: AsyncSession, document_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
    )
    return result.scalar_one()


async def _embed_document(
    session: AsyncSession, document: SourceDocument, embed: EmbedFn
) -> str:
    chunks = chunk_markdown(document.content)
    if not chunks:
        raise ValueError(f"no chunks produced for document {document.id}")

    # deleting first makes re-embedding over an earlier partial run a no-op
    # even without the count check: the next pass sees zero chunks
    await session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )

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
    await session.commit()
    return "processed"


async def embed_corpus(
    *,
    session_factory: async_sessionmaker | None = None,
    embed: EmbedFn | None = None,
) -> dict[str, int]:
    """Embed every completed document that has no chunks yet.

    Re-running is idempotent: documents that already carry chunks are
    skipped, so a completed document is never embedded twice. Single-process
    one-shot script, matching the existing ingest assumptions.
    """
    session_factory = session_factory or default_session_factory
    embed = embed or get_embedding

    stats = {"processed": 0, "skipped": 0, "failed": 0}
    async with session_factory() as session:
        result = await session.execute(
            select(SourceDocument).where(
                SourceDocument.status == DocumentStatus.completed,
                SourceDocument.deleted_at.is_(None),
            )
        )
        documents = result.scalars().all()
        for document in documents:
            try:
                if await _chunk_count(session, document.id):
                    stats["skipped"] += 1
                    continue
                await _embed_document(session, document, embed)
            except Exception:
                await session.rollback()
                logger.exception("embed_document_failed", document_id=str(document.id))
                stats["failed"] += 1
                continue
            stats["processed"] += 1
    return stats


async def main() -> int:
    print("Embedding corpus ...")
    stats = await embed_corpus()
    print(
        f"Done: {stats['processed']} processed, {stats['skipped']} skipped, "
        f"{stats['failed']} failed"
    )
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
