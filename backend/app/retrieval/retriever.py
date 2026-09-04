"""Semantic retrieval over the shared 10-K corpus via pgvector.

Kept free of any PydanticAI dependency so it can be tested and swapped
independently (issue 06 adds a full-text leg and RRF fusion inside
``search`` without touching callers).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import SourcePassage
from app.core.config import settings
from app.core.embeddings import EmbedFn

# Raw SQL with a text-cast vector, same pattern proven in ingest/smoke.py:
# binding the ORM VECTOR type would require registering an asyncpg codec,
# which the cast approach sidesteps entirely.
_SEARCH_SQL = text(
    "SELECT c.id, c.document_id, c.chunk_index, c.content, c.metadata_json, "
    "d.title, d.source_url, d.metadata_json AS doc_meta, "
    "1 - (c.embedding <=> CAST(:vector AS vector)) AS score "
    "FROM document_chunks c "
    "JOIN source_documents d ON d.id = c.document_id "
    "JOIN users u ON u.id = d.user_id "
    "WHERE u.email = :corpus_owner_email "
    "AND d.deleted_at IS NULL "
    "AND c.embedding IS NOT NULL "
    "ORDER BY c.embedding <=> CAST(:vector AS vector) "
    "LIMIT :limit"
)


class PgVectorRetriever:
    def __init__(
        self,
        session: AsyncSession,
        embed: EmbedFn,
        top_k: int | None = None,
    ) -> None:
        self.session = session
        self.embed = embed
        self.top_k = top_k if top_k is not None else settings.retrieval_top_k

    async def search(self, query: str) -> list[SourcePassage]:
        """Return the top-K passages nearest to ``query`` in cosine space.

        An empty corpus yields ``[]`` rather than an error — the agent is
        expected to declare insufficient evidence in that case.
        """
        vectors = await self.embed([query])
        rows = (
            await self.session.execute(
                _SEARCH_SQL,
                {
                    "vector": str(list(vectors[0])),
                    "corpus_owner_email": settings.corpus_owner_email,
                    "limit": self.top_k,
                },
            )
        ).mappings()

        passages = [
            SourcePassage(
                chunk_id=str(row["id"]),
                document_id=str(row["document_id"]),
                chunk_index=row["chunk_index"],
                content=row["content"],
                score=float(row["score"]),
                section_path=row["metadata_json"].get("section_path") or "",
                title=row["title"],
                ticker=row["doc_meta"].get("ticker"),
                form=row["doc_meta"].get("form"),
                filing_date=row["doc_meta"].get("filing_date"),
                source_url=row["source_url"],
            )
            for row in rows
        ]
        return passages
