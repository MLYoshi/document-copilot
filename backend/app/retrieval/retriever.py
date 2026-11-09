from sqlalchemy import text

from app.assistant.outputs import SourcePassage
from app.core.config import settings
from app.core.embeddings import EmbedFn
from app.database.session import session_factory

_SUMMARY_SEARCH_SQL = text(
    "SELECT d.id, d.id AS document_id, 0 AS passage_index, "
    "d.content, d.title, d.source_url, "
    "d.metadata_json AS doc_meta "
    "FROM source_documents d "
    "JOIN auth.users u ON u.id = d.user_id "
    "WHERE u.email = :corpus_owner_email "
    "AND d.deleted_at IS NULL "
    "AND d.status = 'completed' "
    "AND d.summary_embedding IS NOT NULL "
    "ORDER BY d.summary_embedding <=> CAST(:vector AS vector) "
    "LIMIT :limit"
)


def _to_passage(row) -> SourcePassage:
    return SourcePassage(
        passage_id=str(row["id"]),
        document_id=str(row["document_id"]),
        passage_index=row["passage_index"],
        content=row["content"],
        score=0.0,
        section_path="",
        title=row["title"],
        ticker=row["doc_meta"].get("ticker"),
        form=row["doc_meta"].get("form"),
        filing_date=row["doc_meta"].get("filing_date"),
        source_url=row["source_url"],
    )


class PgVectorRetriever:
    def __init__(self, embed: EmbedFn, top_k: int | None = None) -> None:
        self.embed = embed
        self.top_k = top_k if top_k is not None else settings.retrieval_top_k

    async def search(self, query: str) -> list[SourcePassage]:
        """Rank by summary embeddings and return complete original filings."""
        vectors = await self.embed([query])
        async with session_factory() as session:
            rows = (
                await session.execute(
                    _SUMMARY_SEARCH_SQL,
                    {
                        "vector": str(list(vectors[0])),
                        "corpus_owner_email": settings.corpus_owner_email,
                        "limit": self.top_k,
                    },
                )
            ).mappings()
            return [_to_passage(row) for row in rows]
