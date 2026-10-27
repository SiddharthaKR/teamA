"""Shared SQLAlchemy models for persistent application data."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    normalized_username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), onupdate=func.now()
    )


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    role: Mapped[str] = mapped_column(String(256))
    tasks: Mapped[list[str]] = mapped_column(JSON)
    tools_domain: Mapped[str | None] = mapped_column(Text(), nullable=True)
    declared_level: Mapped[str] = mapped_column(String(32))
    estimated_working_level: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    level_source: Mapped[str] = mapped_column(String(32), default="self-reported")
    level_confidence: Mapped[float] = mapped_column(Float(), default=1.0)
    romaji_preference: Mapped[bool] = mapped_column(Boolean(), default=False)
    milestone_id: Mapped[str] = mapped_column(String(32), default="get-by", server_default="get-by")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), onupdate=func.now()
    )


class PersonalTerm(Base):
    __tablename__ = "personal_terms"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "expression", name="uq_personal_term"),
        CheckConstraint("kind IN ('word', 'grammar')", name="ck_personal_term_kind"),
        CheckConstraint("importance IN ('S', 'A', 'B')", name="ck_personal_term_importance"),
        CheckConstraint("status IN ('active', 'hidden')", name="ck_personal_term_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    expression: Mapped[str] = mapped_column(String(100))
    reference_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reading: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meaning: Mapped[str | None] = mapped_column(String(100), nullable=True)
    importance: Mapped[str] = mapped_column(String(1), default="A")
    status: Mapped[str] = mapped_column(String(16), default="active")
    source: Mapped[str] = mapped_column(String(16), default="pasted")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class LearningItem(Base):
    __tablename__ = "learning_items"
    __table_args__ = (
        CheckConstraint(
            "category IN ('kanji', 'vocabulary', 'grammar')",
            name="ck_learning_item_category",
        ),
        CheckConstraint(
            "jlpt_confidence >= 0.0 AND jlpt_confidence <= 1.0",
            name="ck_learning_item_jlpt_confidence",
        ),
    )

    canonical_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    category: Mapped[str] = mapped_column(String(32))
    # Reference-list spelling (dictionary or curated grammar list), never learner
    # text; None when the item is not in the reference data.
    expression: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jlpt_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    jlpt_provenance: Mapped[str] = mapped_column(String(32))
    jlpt_confidence: Mapped[float] = mapped_column(Float())
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())


class UserItemProgress(Base):
    __tablename__ = "user_item_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_progress_user_item"),
        CheckConstraint("exposure_count >= 0", name="ck_progress_exposure_count"),
        CheckConstraint("correct_count >= 0", name="ck_progress_correct_count"),
        CheckConstraint("incorrect_count >= 0", name="ck_progress_incorrect_count"),
        CheckConstraint(
            "mastery_score >= 0.0 AND mastery_score <= 1.0",
            name="ck_progress_mastery_score",
        ),
        CheckConstraint(
            "sm2_ease >= 1.3 AND sm2_ease <= 3.0",
            name="ck_progress_sm2_ease",
        ),
        CheckConstraint(
            "sm2_interval_days >= 0", name="ck_progress_sm2_interval_days"
        ),
        CheckConstraint(
            "consecutive_successful_reviews >= 0",
            name="ck_progress_consecutive_successful_reviews",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("learning_items.canonical_id", ondelete="RESTRICT"), index=True
    )
    exposure_count: Mapped[int] = mapped_column(Integer(), default=0)
    correct_count: Mapped[int] = mapped_column(Integer(), default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer(), default=0)
    mastery_score: Mapped[float] = mapped_column(Float(), default=0.0)
    dimension_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    consecutive_successful_reviews: Mapped[int] = mapped_column(Integer(), default=0)
    sm2_interval_days: Mapped[int] = mapped_column(Integer(), default=0)
    sm2_ease: Mapped[float] = mapped_column(Float(), default=2.5)
    last_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="t05-v2", server_default="t05-v2")
    last_answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(), nullable=True
    )
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), onupdate=func.now()
    )


class ReviewAttempt(Base):
    __tablename__ = "review_attempts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_attempt_user_idempotency"
        ),
        CheckConstraint(
            "question_form IN ('meaning', 'reading', 'contextual_cloze', 'register')",
            name="ck_attempt_question_form",
        ),
        CheckConstraint(
            "answer_confidence IN ('sure', 'guessed')",
            name="ck_attempt_answer_confidence",
        ),
        CheckConstraint(
            "skill_dimension IN ('recognition', 'reading', 'contextual_use', "
            "'grammar_application')",
            name="ck_attempt_skill_dimension",
        ),
        CheckConstraint(
            "outcome IN ('again', 'hard', 'good', 'easy')",
            name="ck_attempt_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("learning_items.canonical_id", ondelete="RESTRICT"), index=True
    )
    lesson_session_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    question_form: Mapped[str] = mapped_column(String(32))
    skill_dimension: Mapped[str] = mapped_column(String(32))
    answer_confidence: Mapped[str] = mapped_column(String(16), default="sure")
    is_correct: Mapped[bool] = mapped_column(Boolean())
    is_retry: Mapped[bool] = mapped_column(Boolean(), default=False)
    # False for practice questions whose key code could not verify: the answer is
    # logged for completion and analytics but never changes mastery or schedules.
    is_graded: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    outcome: Mapped[str] = mapped_column(String(16))
    policy_version: Mapped[str] = mapped_column(String(16))
    answered_at: Mapped[datetime] = mapped_column(DateTime())


class CompletedLessonMetadata(Base):
    __tablename__ = "completed_lesson_metadata"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "lesson_session_id", name="uq_completion_user_session"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lesson_session_id: Mapped[str] = mapped_column(String(36))
    topic_id: Mapped[str] = mapped_column(String(128))
    difficulty: Mapped[str] = mapped_column(String(32))
    studied_item_ids: Mapped[list[str]] = mapped_column(JSON)
    completed_at: Mapped[datetime] = mapped_column(DateTime())


class ContentReview(Base):
    """A team reviewer's verdict on one generated item, question or line (decision 9).

    Reviewer mode only. Unlike learner data, the snapshot keeps the reviewed text,
    because judging accuracy needs it; reviewers are told not to use work data.
    """

    __tablename__ = "content_reviews"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "lesson_session_id", "target_kind", "target_id",
            name="uq_review_target",
        ),
        CheckConstraint(
            "target_kind IN ('item', 'question', 'line', 'lesson')", name="ck_review_target_kind"
        ),
        CheckConstraint("verdict IN ('ok', 'wrong')", name="ck_review_verdict"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lesson_session_id: Mapped[str] = mapped_column(String(36), index=True)
    target_kind: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(128))
    verdict: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    versions: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime())
