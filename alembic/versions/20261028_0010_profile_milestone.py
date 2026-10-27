"""Add a learner-chosen milestone with a safe default for existing profiles.

Revision ID: 20261028_0010
Revises: 20261024_0009
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261028_0010"
down_revision: str | None = "20261024_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learner_profiles") as batch:
        batch.add_column(
            sa.Column("milestone_id", sa.String(length=32), nullable=False, server_default="get-by")
        )


def downgrade() -> None:
    with op.batch_alter_table("learner_profiles") as batch:
        batch.drop_column("milestone_id")
