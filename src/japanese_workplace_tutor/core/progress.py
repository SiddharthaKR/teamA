"""Learning progress as a pure function of answer evidence.

Mastery and the review schedule are computed here, from the answer log, by a
versioned policy. Nothing in this module reads a database or calls a model, so
the same evidence always produces the same state, and a new scheduler (for
example FSRS) can be introduced later by replaying the stored evidence.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from math import ceil
from typing import Protocol

from .items import AnswerConfidence, ItemCategory, QuestionForm, ReviewOutcome, SkillDimension


@dataclass(frozen=True)
class ProgressRecord:
    item_id: str
    category: ItemCategory
    exposure_count: int
    correct_count: int
    incorrect_count: int
    mastery_score: float
    dimension_scores: dict[str, float]
    consecutive_successful_reviews: int
    sm2_interval_days: int
    sm2_ease: float
    last_outcome: ReviewOutcome | None
    last_answered_at: datetime | None
    next_review_at: datetime | None
    # Reference-list spelling of the item (never learner text); None for items
    # saved before names were stored or not found in the reference data.
    expression: str | None = None

@dataclass(frozen=True)
class PastAttempt:
    """The slice of an earlier answer that the policy may look at."""

    lesson_session_id: str
    question_form: str
    is_correct: bool


@dataclass(frozen=True)
class Answer:
    """One submitted answer, as evidence."""

    question_form: QuestionForm
    skill_dimension: SkillDimension
    lesson_session_id: str
    is_correct: bool
    is_retry: bool
    confidence: AnswerConfidence
    answered_at: datetime


@dataclass(frozen=True)
class ItemState:
    """Derived progress for one learner and one item. Defaults match a new item."""

    mastery_score: float = 0.0
    dimension_scores: Mapping[str, float] = field(default_factory=dict)
    consecutive_successful_reviews: int = 0
    sm2_interval_days: int = 0
    sm2_ease: float = 2.5
    next_review_at: datetime | None = None
    last_outcome: str | None = None


class ProgressPolicy(Protocol):
    version: str

    def outcome(
        self, state: ItemState, history: Sequence[PastAttempt], answer: Answer
    ) -> ReviewOutcome: ...

    def apply(
        self,
        state: ItemState,
        history: Sequence[PastAttempt],
        answer: Answer,
        outcome: ReviewOutcome,
    ) -> ItemState: ...


def skill_dimension(form: QuestionForm, category: ItemCategory) -> SkillDimension:
    if form is QuestionForm.READING:
        return SkillDimension.READING
    if form is QuestionForm.REGISTER:
        return SkillDimension.CONTEXTUAL_USE
    if form is QuestionForm.CONTEXTUAL_CLOZE:
        if category is ItemCategory.GRAMMAR:
            return SkillDimension.GRAMMAR_APPLICATION
        return SkillDimension.CONTEXTUAL_USE
    return SkillDimension.RECOGNITION


class SM2MasteryPolicy:
    """Policy t05-v1: evidence-mapped outcomes, capped mastery, simplified SM-2."""

    version = "t05-v1"
    MASTERY_THRESHOLD = 0.80
    MASTERY_DELTAS = {
        ReviewOutcome.AGAIN: -0.08,
        ReviewOutcome.HARD: 0.08,
        ReviewOutcome.GOOD: 0.18,
        ReviewOutcome.EASY: 0.30,
    }
    DIMENSION_DELTAS = {
        ReviewOutcome.AGAIN: -0.10,
        ReviewOutcome.HARD: 0.10,
        ReviewOutcome.GOOD: 0.20,
        ReviewOutcome.EASY: 0.30,
    }
    AGAIN_REVIEW_DELAY = timedelta(minutes=10)

    def outcome(
        self, state: ItemState, history: Sequence[PastAttempt], answer: Answer
    ) -> ReviewOutcome:
        if not answer.is_correct:
            return ReviewOutcome.AGAIN
        if answer.is_retry:
            return ReviewOutcome.HARD
        successful_sessions = {
            attempt.lesson_session_id for attempt in history if attempt.is_correct
        }
        successful_forms = {attempt.question_form for attempt in history if attempt.is_correct}
        successful_forms.add(answer.question_form.value)
        separate_sessions = len(successful_sessions - {answer.lesson_session_id}) >= 2
        if (
            state.consecutive_successful_reviews >= 2
            and separate_sessions
            and len(successful_forms) >= 2
        ):
            # A guessed answer can never earn the strongest outcome.
            if answer.confidence is AnswerConfidence.GUESSED:
                return ReviewOutcome.GOOD
            return ReviewOutcome.EASY
        return ReviewOutcome.GOOD

    def apply(
        self,
        state: ItemState,
        history: Sequence[PastAttempt],
        answer: Answer,
        outcome: ReviewOutcome,
    ) -> ItemState:
        now = answer.answered_at
        dimension_scores = dict(state.dimension_scores or {})
        current_dimension = dimension_scores.get(answer.skill_dimension.value, 0.0)
        # A guessed correct answer is weaker evidence than a confident one.
        damping = (
            0.5
            if answer.confidence is AnswerConfidence.GUESSED and outcome is not ReviewOutcome.AGAIN
            else 1.0
        )
        dimension_scores[answer.skill_dimension.value] = round(
            min(1.0, max(0.0, current_dimension + self.DIMENSION_DELTAS[outcome] * damping)),
            2,
        )

        mastery = state.mastery_score + self.MASTERY_DELTAS[outcome] * damping
        successful_forms = {attempt.question_form for attempt in history if attempt.is_correct}
        if outcome is not ReviewOutcome.AGAIN:
            successful_forms.add(answer.question_form.value)
        if len(successful_forms) < 2 or outcome is not ReviewOutcome.EASY:
            mastery = min(mastery, self.MASTERY_THRESHOLD - 0.01)
        mastery_score = round(min(1.0, max(0.0, mastery)), 2)

        consecutive = state.consecutive_successful_reviews
        ease = state.sm2_ease
        interval = state.sm2_interval_days
        if outcome is ReviewOutcome.AGAIN:
            consecutive = 0
            ease = round(max(1.3, ease - 0.20), 2)
            interval = 0
            next_review_at = now + self.AGAIN_REVIEW_DELAY
        elif outcome is ReviewOutcome.HARD:
            consecutive = 0
            ease = round(max(1.3, ease - 0.15), 2)
            interval = 1
            next_review_at = now + timedelta(days=1)
        elif outcome is ReviewOutcome.GOOD:
            consecutive += 1
            ease = round(min(3.0, ease + 0.05), 2)
            if interval == 0:
                interval = 1
            elif interval == 1:
                interval = 3
            else:
                interval = ceil(interval * ease)
            next_review_at = now + timedelta(days=interval)
        else:
            consecutive += 1
            ease = round(min(3.0, ease + 0.15), 2)
            interval = ceil(max(4, interval) * ease * 1.3)
            next_review_at = now + timedelta(days=interval)
        return replace(
            state,
            mastery_score=mastery_score,
            dimension_scores=dimension_scores,
            consecutive_successful_reviews=consecutive,
            sm2_interval_days=interval,
            sm2_ease=ease,
            next_review_at=next_review_at,
            last_outcome=outcome.value,
        )


def replay(
    policy: ProgressPolicy, answers: Sequence[Answer], initial: ItemState | None = None
) -> tuple[ItemState, tuple[ReviewOutcome, ...]]:
    """Recompute one item's state from its ordered answer log."""

    state = initial or ItemState()
    history: list[PastAttempt] = []
    outcomes: list[ReviewOutcome] = []
    for answer in answers:
        outcome = policy.outcome(state, history, answer)
        state = policy.apply(state, history, answer, outcome)
        outcomes.append(outcome)
        history.append(
            PastAttempt(answer.lesson_session_id, answer.question_form.value, answer.is_correct)
        )
    return state, tuple(outcomes)


class ItemStatus(StrEnum):
    NEW = "new"  # seen in a lesson, never answered
    LEARNING = "learning"
    MASTERED = "mastered"
    SLIPPING = "slipping"  # answered wrong last time, or a review is well overdue


MASTERY_THRESHOLD = SM2MasteryPolicy.MASTERY_THRESHOLD


def item_status(record: ProgressRecord, now: datetime) -> ItemStatus:
    """Learner-facing status: a pure function of the stored progress."""

    if record.last_outcome is None:
        return ItemStatus.NEW
    if record.last_outcome is ReviewOutcome.AGAIN:
        return ItemStatus.SLIPPING
    if record.next_review_at is not None:
        grace = timedelta(days=max(1, record.sm2_interval_days // 2))
        if now - record.next_review_at > grace:
            return ItemStatus.SLIPPING
    if record.mastery_score >= MASTERY_THRESHOLD:
        return ItemStatus.MASTERED
    return ItemStatus.LEARNING
