import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DocumentTable(Base):
    __tablename__ = "document_tables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # DOM order within the document; matches the [Table N: caption] placeholder
    # in the ingested markdown so chunks can be linked back to tables.
    table_index: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    section_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    # 2D array of cell strings; JSONB keeps each table self-contained with no
    # cross-row JOIN overhead. No vector index — tables are not embedded.
    rows: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("uq_document_tables_order", "document_id", "table_index", unique=True),
    )
