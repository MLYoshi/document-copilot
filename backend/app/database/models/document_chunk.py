import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Computed, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.source_document import SourceDocument


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # page, section, source offsets, ...
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Width follows settings rather than a literal: pgvector will not cast
    # between widths, so a column that disagrees with what the embedder returns
    # only fails on the first real write — after the embeddings are paid for.
    # The migration must be retyped alongside; tests/ingest/test_schema.py
    # guards the pair.
    embedding = mapped_column(VECTOR(settings.embedding_dimensions), nullable=True)
    search_vector = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=False,
    )

    document: Mapped["SourceDocument"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index(
            "document_chunks_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("document_chunks_search_vector_idx", "search_vector", postgresql_using="gin"),
        Index("document_chunks_metadata_idx", "metadata_json", postgresql_using="gin"),
        Index("uq_document_chunks_order", "document_id", "chunk_index", unique=True),
    )
