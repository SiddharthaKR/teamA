"""Learning items keep their reference-list name (progress view, due reviews).

Revision ID: 20261024_0009
Revises: 20261024_0008
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261024_0009"
down_revision: str | None = "20261024_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learning_items") as batch:
        batch.add_column(sa.Column("expression", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("learning_items") as batch:
        batch.drop_column("expression")
