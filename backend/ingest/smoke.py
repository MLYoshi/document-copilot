"""Pre-flight for the ingest pipeline, over a handful of real chunks.

Runs the whole paid path once — extract, chunk, embed through OpenRouter, write
to pgvector, read back — on the first few chunks of one filing, then deletes
what it wrote. Costs a fraction of a cent and a few seconds; run it before
paying to embed the corpus, because the failures it catches (a dead API key, a
model that ignores `dimensions`, a column the wrong width) otherwise surface
halfway through a full run, after the money is spent.

Three chunks, not one, so the nearest-neighbour read-back below has something
to be wrong about: with a single row, "the closest vector to X is X" is true by
construction and proves nothing about the HNSW index.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.embeddings import EmbedFn, get_embedding
from app.database.models import DocumentChunk, SourceDocument
from app.database.session import session_factory as default_session_factory
from ingest.chunker import chunk_markdown
from ingest.extractor import extract_markdown
from ingest.pipeline import seed_corpus_owner

logger = structlog.get_logger()

DEFAULT_DOWNLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "downloads"
DEFAULT_CHUNK_COUNT = 3
# an accession the real corpus can never contain, so the cleanup in run_smoke
# cannot delete anything but its own rows
SMOKE_ACCESSION = "smoke-test-local"


@dataclass
class SmokeReport:
    model: str
    dimensions: int
    chunks_written: int
    preview: str


async def run_smoke(
    downloads_dir: Path,
    *,
    session_factory: async_sessionmaker | None = None,
    embed: EmbedFn | None = None,
    chunk_count: int = DEFAULT_CHUNK_COUNT,
) -> SmokeReport:
    """Embed, store and read back ``chunk_count`` chunks of the first filing."""
    session_factory = session_factory or default_session_factory
    embed = embed or get_embedding

    manifest = json.loads((downloads_dir / "manifest.json").read_text(encoding="utf-8"))
    filing = manifest["filings"][0]
    html = (downloads_dir / filing["local_path"]).read_text(encoding="utf-8")
    chunks = chunk_markdown(extract_markdown(html))[:chunk_count]
    if not chunks:
        raise ValueError(f"no chunks extracted from {filing['local_path']}")

    vectors = await embed([chunk.content for chunk in chunks])
    for index, vector in enumerate(vectors):
        if len(vector) != settings.embedding_dimensions:
            raise ValueError(
                f"chunk {index}: {settings.embedding_model} returned "
                f"{len(vector)} dimensions, expected {settings.embedding_dimensions}"
            )

    async with session_factory() as session:
        owner = await seed_corpus_owner(session)
        document = SourceDocument(
            user_id=owner.id,
            title=f"smoke test: {filing['ticker']} {filing['form']}",
            metadata_json={**filing, "accession_number": SMOKE_ACCESSION},
            content="\n\n".join(chunk.content for chunk in chunks),
        )
        session.add(document)
        await session.flush()

        for chunk, vector in zip(chunks, vectors, strict=True):
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

        # rollback() below expires ORM objects, so hold on to the id instead
        document_id = document.id
        try:
            return await _verify(session, document_id, vectors[0])
        finally:
            # the rows are already committed, so discarding this transaction
            # loses nothing — and it is required for the delete to run at all
            # when _verify failed and left the transaction aborted
            await session.rollback()
            await session.execute(
                delete(SourceDocument).where(SourceDocument.id == document_id)
            )
            await session.commit()


async def _verify(
    session, document_id: uuid.UUID, query_vector: list[float]
) -> SmokeReport:
    """Read the rows back and confirm the vector column is queryable."""
    stored = (
        (
            await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )
    if not stored:
        raise ValueError("smoke chunks vanished before they could be read back")

    for chunk in stored:
        if len(chunk.embedding) != settings.embedding_dimensions:
            raise ValueError(
                f"chunk {chunk.chunk_index} came back {len(chunk.embedding)}-dimensional, "
                f"expected {settings.embedding_dimensions}"
            )
        # an empty section_path is legitimate — the cover page of a 10-K sits
        # before any heading — but a missing key means the chunker and the
        # stored schema have drifted apart
        if "section_path" not in chunk.metadata_json:
            raise ValueError(
                f"chunk {chunk.chunk_index} has no section_path key: "
                "the chunker no longer matches the document schema"
            )

    # the nearest neighbour of a vector must be the chunk it came from — this
    # is what proves the HNSW index is actually usable, not just present
    nearest = (
        await session.execute(
            text(
                "SELECT id FROM document_chunks "
                "WHERE document_id = :document_id "
                "ORDER BY embedding <=> CAST(:vector AS vector) "
                "LIMIT 1"
            ),
            {"document_id": document_id, "vector": str(list(query_vector))},
        )
    ).scalar_one_or_none()
    if nearest != stored[0].id:
        raise ValueError(
            "vector round-trip failed: the nearest neighbour of chunk 0 is not "
            "chunk 0 itself"
        )

    return SmokeReport(
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        chunks_written=len(stored),
        preview=stored[0].content[:80],
    )


async def main() -> None:
    downloads_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOWNLOADS_DIR
    print(f"Smoke-testing ingest against {downloads_dir} ...")
    report = await run_smoke(downloads_dir)
    print(
        f"OK — {report.chunks_written} chunk(s) embedded with {report.model} "
        f"({report.dimensions}d), written to pgvector, read back, deleted.\n"
        f"First chunk: {report.preview!r}"
    )


if __name__ == "__main__":
    asyncio.run(main())
