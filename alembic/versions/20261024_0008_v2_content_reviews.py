"""Team accuracy review verdicts (reviewer mode).

Revision ID: 20261024_0008
Revises: 20261024_0007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261024_0008"
down_revision: str | None = "20261024_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_session_id", sa.String(length=36), nullable=False),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("verdict", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("versions", sa.JSON(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "lesson_session_id", "target_kind", "target_id", name="uq_review_target"
        ),
        sa.CheckConstraint(
            "target_kind IN ('item', 'question', 'line', 'lesson')", name="ck_review_target_kind"
        ),
        sa.CheckConstraint("verdict IN ('ok', 'wrong')", name="ck_review_verdict"),
    )
    op.create_index("ix_content_reviews_user_id", "content_reviews", ["user_id"])
    op.create_index("ix_content_reviews_lesson_session_id", "content_reviews", ["lesson_session_id"])


def downgrade() -> None:
    op.drop_index("ix_content_reviews_lesson_session_id", table_name="content_reviews")
    op.drop_index("ix_content_reviews_user_id", table_name="content_reviews")
    op.drop_table("content_reviews")
