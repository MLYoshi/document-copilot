"""Hybrid retrieval over the shared 10-K corpus.

Two legs run against the same corpus filter — pgvector cosine (semantic)
and Postgres full-text via the chunks' tsvector column (keyword) — and
Reciprocal Rank Fusion merges the two ranked id lists. Kept free of any
PydanticAI dependency so it can be tested and swapped independently.
"""
from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import SourcePassage
from app.core.config import settings
from app.core.embeddings import EmbedFn
from app.retrieval.rrf import fuse

# Raw SQL with a text-cast vector, same pattern proven in ingest/smoke.py:
# binding the ORM VECTOR type would require registering an asyncpg codec,
# which the cast approach sidesteps entirely.
_OWNER_FILTER = (
    "JOIN source_documents d ON d.id = c.document_id "
    "JOIN users u ON u.id = d.user_id "
    "WHERE u.email = :corpus_owner_email "
    "AND d.deleted_at IS NULL "
)

_PASSAGE_COLUMNS = (
    "c.id, c.document_id, c.chunk_index, c.content, c.metadata_json, "
    "d.title, d.source_url, d.metadata_json AS doc_meta "
)

# Rank-only legs: chunk ids in best-first order, kept lean because only the
# ordering feeds RRF; passage bodies are fetched once for the fused winners.
_SEMANTIC_RANK_SQL = text(
    "SELECT c.id FROM document_chunks c "
    + _OWNER_FILTER
    + "AND c.embedding IS NOT NULL "
    "ORDER BY c.embedding <=> CAST(:vector AS vector) "
    "LIMIT :limit"
)

_FULLTEXT_RANK_SQL = text(
    "SELECT c.id FROM document_chunks c "
    + _OWNER_FILTER
    + "AND c.search_vector @@ websearch_to_tsquery('english', :query) "
    "ORDER BY ts_rank_cd(c.search_vector, websearch_to_tsquery('english', :query)) DESC "
    "LIMIT :limit"
)

_BY_IDS_SQL = text(
    f"SELECT {_PASSAGE_COLUMNS} FROM document_chunks c "
    + _OWNER_FILTER
    + "AND c.id IN :ids"
).bindparams(bindparam("ids", expanding=True))


def _to_passage(row) -> SourcePassage:
    return SourcePassage(
        chunk_id=str(row["id"]),
        document_id=str(row["document_id"]),
        chunk_index=row["chunk_index"],
        content=row["content"],
        score=0.0,
        section_path=row["metadata_json"].get("section_path") or "",
        title=row["title"],
        ticker=row["doc_meta"].get("ticker"),
        form=row["doc_meta"].get("form"),
        filing_date=row["doc_meta"].get("filing_date"),
        source_url=row["source_url"],
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
        """Hybrid search: semantic + full-text legs fused with RRF.

        The legs run sequentially on the shared AsyncSession (asyncpg forbids
        concurrent statements on one connection); both are index-backed so the
        added latency is one cheap query. An empty corpus yields ``[]`` rather
        than an error — the agent is expected to declare insufficient
        evidence in that case.
        """
        vectors = await self.embed([query])
        semantic_ids = [
            str(row[0])
            for row in await self.session.execute(
                _SEMANTIC_RANK_SQL,
                {
                    "vector": str(list(vectors[0])),
                    "corpus_owner_email": settings.corpus_owner_email,
                    "limit": settings.retrieval_fetch_depth,
                },
            )
        ]
        fulltext_ids = [
            str(row[0])
            for row in await self.session.execute(
                _FULLTEXT_RANK_SQL,
                {
                    "query": query,
                    "corpus_owner_email": settings.corpus_owner_email,
                    "limit": settings.retrieval_fetch_depth,
                },
            )
        ]

        fused = fuse(semantic_ids, fulltext_ids, k=settings.rrf_k)[: self.top_k]
        if not fused:
            return []

        by_id = await self._fetch_by_ids([chunk_id for chunk_id, _ in fused])
        return [
            by_id[chunk_id].model_copy(update={"score": score})
            for chunk_id, score in fused
        ]

    async def get_chunks(
        self,
        chunk_ids: list[str],
        *,
        neighbor_window: int | None = None,
    ) -> list[SourcePassage]:
        """Fetch full chunk bodies by id, plus adjacent chunks for context.

        Neighbors are the ``neighbor_window`` chunks on each side within the
        same document (chunk_index is contiguous per document), so the agent
        can read across chunk boundaries when grounding a quote that a
        chunker split in half. Results are ordered by document and chunk
        position, not by request order.
        """
        window = (
            neighbor_window
            if neighbor_window is not None
            else settings.read_chunk_window
        )
        targets = await self._fetch_by_ids(chunk_ids)
        if not targets or window < 1:
            return sorted(targets.values(), key=_passage_order)

        clauses = []
        params = {"corpus_owner_email": settings.corpus_owner_email}
        for i, passage in enumerate(targets.values()):
            clauses.append(
                f"(c.document_id = :doc{i} "
                f"AND c.chunk_index BETWEEN :lo{i} AND :hi{i})"
            )
            params[f"doc{i}"] = passage.document_id
            params[f"lo{i}"] = passage.chunk_index - window
            params[f"hi{i}"] = passage.chunk_index + window

        rows = (
            await self.session.execute(
                text(
                    f"SELECT {_PASSAGE_COLUMNS} FROM document_chunks c "
                    + _OWNER_FILTER
                    + f"AND ({' OR '.join(clauses)})"
                ),
                params,
            )
        ).mappings()

        merged = dict(targets)
        for row in rows:
            passage = _to_passage(row)
            merged.setdefault(passage.chunk_id, passage)
        return sorted(merged.values(), key=_passage_order)

    async def _fetch_by_ids(self, chunk_ids: list[str]) -> dict[str, SourcePassage]:
        rows = (
            await self.session.execute(
                _BY_IDS_SQL,
                {
                    "ids": [str(chunk_id) for chunk_id in chunk_ids],
                    "corpus_owner_email": settings.corpus_owner_email,
                },
            )
        ).mappings()
        return {str(row["id"]): _to_passage(row) for row in rows}


def _passage_order(passage: SourcePassage) -> tuple[str, int]:
    return (passage.document_id, passage.chunk_index)
