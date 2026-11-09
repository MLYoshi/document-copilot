from collections.abc import Sequence

from alembic import op

revision: str = "0004_drop_answer_run_tables"
down_revision: str | Sequence[str] | None = "0003_answer_run_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("answer_run_events")
    op.drop_table("answer_runs")


def downgrade() -> None:
    raise NotImplementedError("Restore 0003_answer_run_events before downgrading")
