"""Mark prior progress for replay under the separate-day policy.

Revision ID: 20261028_0012
Revises: 20261028_0011
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261028_0012"
down_revision: str | None = "20261028_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_item_progress") as batch:
        batch.add_column(sa.Column("policy_version", sa.String(32), nullable=False,
                                   server_default="t05-v1"))


def downgrade() -> None:
    with op.batch_alter_table("user_item_progress") as batch:
        batch.drop_column("policy_version")
