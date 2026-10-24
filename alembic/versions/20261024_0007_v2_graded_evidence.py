"""Mark each answer as graded or practice-only (code-verified answer keys).

Revision ID: 20261024_0007
Revises: 20260903_0006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261024_0007"
down_revision: str | None = "20260903_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("review_attempts") as batch_op:
        batch_op.add_column(
            sa.Column("is_graded", sa.Boolean(), server_default=sa.true(), nullable=False)
        )


def downgrade() -> None:
    op.execute("DELETE FROM review_attempts WHERE is_graded = 0")
    with op.batch_alter_table("review_attempts") as batch_op:
        batch_op.drop_column("is_graded")
