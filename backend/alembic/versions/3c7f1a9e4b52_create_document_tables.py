"""create document_tables

Revision ID: 3c7f1a9e4b52
Revises: 29baa7ace0d1
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3c7f1a9e4b52'
down_revision: Union[str, Sequence[str], None] = '29baa7ace0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('document_tables',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('table_index', sa.Integer(), nullable=False),
    sa.Column('caption', sa.Text(), nullable=True),
    sa.Column('section_path', sa.Text(), nullable=True),
    sa.Column('markdown', sa.Text(), nullable=False),
    sa.Column('rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['source_documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_tables_document_id'), 'document_tables', ['document_id'], unique=False)
    op.create_index('uq_document_tables_order', 'document_tables', ['document_id', 'table_index'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_document_tables_order', table_name='document_tables')
    op.drop_index(op.f('ix_document_tables_document_id'), table_name='document_tables')
    op.drop_table('document_tables')
