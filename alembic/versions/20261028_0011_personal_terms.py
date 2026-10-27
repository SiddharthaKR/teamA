"""Store user-scoped parsed personal terms.

Revision ID: 20261028_0011
Revises: 20261028_0010
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261028_0011"
down_revision: str | None = "20261028_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_terms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("expression", sa.String(100), nullable=False),
        sa.Column("reference_id", sa.String(128), nullable=True),
        sa.Column("reading", sa.String(100), nullable=True),
        sa.Column("meaning", sa.String(100), nullable=True),
        sa.Column("importance", sa.String(1), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "kind", "expression", name="uq_personal_term"),
        sa.CheckConstraint("kind IN ('word', 'grammar')", name="ck_personal_term_kind"),
        sa.CheckConstraint("importance IN ('S', 'A', 'B')", name="ck_personal_term_importance"),
        sa.CheckConstraint("status IN ('active', 'hidden')", name="ck_personal_term_status"),
    )
    op.create_index("ix_personal_terms_user_id", "personal_terms", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_personal_terms_user_id", table_name="personal_terms")
    op.drop_table("personal_terms")
