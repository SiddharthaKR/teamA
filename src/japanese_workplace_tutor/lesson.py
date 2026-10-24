"""Deterministic fixture lesson and compact, user-scoped learning evidence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

# Domain value types live in the pure core; they are re-exported here because the
# app and tests import them from this module.
from .core.items import (  # noqa: F401
    AnswerConfidence,
    FixtureItem,
    FixtureLesson,
    FixtureQuestion,
    ItemCategory,
    LessonContent,
    LessonExplanationPoint,
    LessonLineExplanation,
    QuestionForm,
    ReviewOutcome,
    SkillDimension,
    display_options,
)
from .core.progress import (  # noqa: F401
    Answer,
    ItemState,
    PastAttempt,
    ProgressRecord,
    SM2MasteryPolicy,
    skill_dimension,
)
from .core.language import LanguageToolkit
from .features.review_questions import build_review
from .schemas.lessons import GeneratedLessonDraft, GeneratedQuiz
from .models import (
    CompletedLessonMetadata,
    LearningItem,
    ReviewAttempt,
    UserItemProgress,
)


FIXTURE_LESSON = FixtureLesson(
    topic_id="fixture-status-update-01",
    title="Giving a concise project status update",
    difficulty="JLPT N4-N3 bridge",
    passage=(
        "田中さん、お疲れさまです。開発の進捗を共有します。新しい機能は予定どおり完成しました。"
        "ただ、テストで問題が見つかったので、リリース日を確認してもよろしいでしょうか。"
        "詳しい状況は午後の会議で報告します。"
    ),
    items=(
        FixtureItem(
            canonical_id="kanji:shin-progress",
            category=ItemCategory.KANJI,
            expression="進",
            reading="しん / すすむ",
            meaning="advance; progress",
            example="作業を進めます。",
            jlpt_level="JLPT N3",
            jlpt_provenance="fixture-reference",
            jlpt_confidence=0.9,
        ),
        FixtureItem(
            canonical_id="vocabulary:shinchoku",
            category=ItemCategory.VOCABULARY,
            expression="進捗",
            reading="しんちょく",
            meaning="progress or status of work",
            example="プロジェクトの進捗を共有します。",
            jlpt_level="JLPT N2",
            jlpt_provenance="fixture-reference",
            jlpt_confidence=0.8,
        ),
        FixtureItem(
            canonical_id="vocabulary:kyouyuu",
            category=ItemCategory.VOCABULARY,
            expression="共有",
            reading="きょうゆう",
            meaning="sharing information",
            example="チームに情報を共有します。",
            jlpt_level="JLPT N3",
            jlpt_provenance="fixture-reference",
            jlpt_confidence=0.8,
        ),
        FixtureItem(
            canonical_id="grammar:permission-temo-yoroshii",
            category=ItemCategory.GRAMMAR,
            expression="〜てもよろしいでしょうか",
            reading="〜てもよろしいでしょうか",
            meaning="may I ...?; a polite request for permission",
            example="予定を変更してもよろしいでしょうか。",
            jlpt_level="JLPT N3",
            jlpt_provenance="fixture-reference",
            jlpt_confidence=0.8,
        ),
        FixtureItem(
            canonical_id="vocabulary:houkoku",
            category=ItemCategory.VOCABULARY,
            expression="報告",
            reading="ほうこく",
            meaning="a report; to report",
            example="会議で結果を報告します。",
            jlpt_level="JLPT N3",
            jlpt_provenance="fixture-reference",
            jlpt_confidence=0.9,
        ),
    ),
    questions=(
        FixtureQuestion(
            question_id="meaning-progress",
            item_id="vocabulary:shinchoku",
            form=QuestionForm.MEANING,
            prompt="In a project update, what does 進捗 mean?",
            options=("Progress of work", "Final approval", "Meeting agenda", "Budget"),
            correct_option_index=0,
            explanation="進捗 describes how far work or a project has progressed.",
        ),
        FixtureQuestion(
            question_id="reading-share",
            item_id="vocabulary:kyouyuu",
            form=QuestionForm.READING,
            prompt="How is 共有 read?",
            options=("きょうゆう", "きょうよう", "こうゆう", "こうよう"),
            correct_option_index=0,
            explanation="共有 is read きょうゆう and means sharing information.",
        ),
        FixtureQuestion(
            question_id="cloze-permission",
            item_id="grammar:permission-temo-yoroshii",
            form=QuestionForm.CONTEXTUAL_CLOZE,
            prompt="Choose the polite phrase: リリース日を確認し___。",
            options=("てもよろしいでしょうか", "てはいけません", "たことがあります", "ながら"),
            correct_option_index=0,
            explanation="〜てもよろしいでしょうか politely asks for permission.",
        ),
        FixtureQuestion(
            question_id="meaning-report",
            item_id="vocabulary:houkoku",
            form=QuestionForm.MEANING,
            prompt="Which action is 報告する?",
            options=("To report", "To postpone", "To approve", "To investigate"),
            correct_option_index=0,
            explanation="報告する means to report information or results.",
        ),
        FixtureQuestion(
            question_id="reading-kanji-progress",
            item_id="kanji:shin-progress",
            form=QuestionForm.READING,
            prompt="What is the reading of 進 in 進捗?",
            options=("しん", "じん", "せん", "ぜん"),
            correct_option_index=0,
            explanation="The on-reading of 進 in 進捗 is しん.",
        ),
    ),
    recap=(
        "Use 進捗, 共有, and 報告 to structure a status update. "
        "Use 〜てもよろしいでしょうか when politely checking permission."
    ),
)

RETRY_QUESTIONS = {
    "meaning-progress": FixtureQuestion(
        question_id="retry-cloze-progress",
        item_id="vocabulary:shinchoku",
        form=QuestionForm.CONTEXTUAL_CLOZE,
        prompt="Choose the project-status word: 開発の___を共有します。",
        options=("進捗", "予算", "承認", "議題"),
        correct_option_index=0,
        explanation="進捗 fits because the sentence is sharing how far development has progressed.",
    ),
    "reading-share": FixtureQuestion(
        question_id="retry-meaning-share",
        item_id="vocabulary:kyouyuu",
        form=QuestionForm.MEANING,
        prompt="What workplace action does 情報を共有する describe?",
        options=("Sharing information", "Approving a budget", "Delaying a meeting", "Testing a release"),
        correct_option_index=0,
        explanation="情報を共有する means to share information with others.",
    ),
    "cloze-permission": FixtureQuestion(
        question_id="retry-meaning-permission",
        item_id="grammar:permission-temo-yoroshii",
        form=QuestionForm.MEANING,
        prompt="What is the purpose of 〜てもよろしいでしょうか?",
        options=("Politely asking permission", "Reporting a past event", "Giving a prohibition", "Comparing two choices"),
        correct_option_index=0,
        explanation="The pattern is a polite way to ask whether an action is permitted.",
    ),
    "meaning-report": FixtureQuestion(
        question_id="retry-cloze-report",
        item_id="vocabulary:houkoku",
        form=QuestionForm.CONTEXTUAL_CLOZE,
        prompt="Choose the action for a meeting update: 会議で結果を___します。",
        options=("報告", "延期", "承認", "調査"),
        correct_option_index=0,
        explanation="報告します means to report the results in the meeting.",
    ),
    "reading-kanji-progress": FixtureQuestion(
        question_id="retry-meaning-kanji-progress",
        item_id="kanji:shin-progress",
        form=QuestionForm.MEANING,
        prompt="Which idea is associated with 進?",
        options=("Advancing", "Stopping", "Returning", "Dividing"),
        correct_option_index=0,
        explanation="進 carries the idea of advancing or moving forward.",
    ),
}

SUPPLEMENTAL_REVIEW_ITEMS = (
    FixtureItem(
        canonical_id="vocabulary:kakunin",
        category=ItemCategory.VOCABULARY,
        expression="確認",
        reading="かくにん",
        meaning="confirmation; checking",
        example="日程を確認します。",
        jlpt_level="JLPT N3",
        jlpt_provenance="fixture-reference",
        jlpt_confidence=0.9,
    ),
    FixtureItem(
        canonical_id="grammar-node",
        category=ItemCategory.GRAMMAR,
        expression="〜ので",
        reading="〜ので",
        meaning="because; giving a reason politely",
        example="問題が見つかったので、確認します。",
        jlpt_level="JLPT N4",
        jlpt_provenance="fixture-reference",
        jlpt_confidence=0.9,
    ),
)

SUPPLEMENTAL_REVIEW_QUESTIONS = (
    FixtureQuestion(
        question_id="review-meaning-confirm",
        item_id="vocabulary:kakunin",
        form=QuestionForm.MEANING,
        prompt="What workplace action does 確認する describe?",
        options=("Checking", "Reporting", "Sharing", "Advancing"),
        correct_option_index=0,
        explanation="確認する means to check or confirm something.",
    ),
    FixtureQuestion(
        question_id="review-reading-confirm",
        item_id="vocabulary:kakunin",
        form=QuestionForm.READING,
        prompt="How is 確認 read?",
        options=("かくにん", "かくじん", "かんにん", "かんじん"),
        correct_option_index=0,
        explanation="確認 is read かくにん.",
    ),
    FixtureQuestion(
        question_id="review-meaning-node",
        item_id="grammar-node",
        form=QuestionForm.MEANING,
        prompt="What relationship does 〜ので express?",
        options=("A reason", "A comparison", "Permission", "A prohibition"),
        correct_option_index=0,
        explanation="〜ので gives a reason, often with a polite or neutral tone.",
    ),
    FixtureQuestion(
        question_id="review-cloze-node",
        item_id="grammar-node",
        form=QuestionForm.CONTEXTUAL_CLOZE,
        prompt="Choose the reason marker: 問題が見つかった___、確認します。",
        options=("ので", "まで", "より", "でも"),
        correct_option_index=0,
        explanation="ので links the discovered problem to the reason for checking.",
    ),
)

REVIEW_ITEMS = (*FIXTURE_LESSON.items, *SUPPLEMENTAL_REVIEW_ITEMS)
_FIXTURE_NAMES = {item.canonical_id: item.expression for item in REVIEW_ITEMS}
REVIEW_QUESTIONS = {
    item.canonical_id: tuple(
        question
        for question in (
            *FIXTURE_LESSON.questions,
            *RETRY_QUESTIONS.values(),
            *SUPPLEMENTAL_REVIEW_QUESTIONS,
        )
        if question.item_id == item.canonical_id
    )
    for item in REVIEW_ITEMS
}


class LessonStateError(ValueError):
    pass


@dataclass(frozen=True)
class ActiveLesson:
    lesson_session_id: str
    lesson: FixtureLesson
    retry_questions: tuple[FixtureQuestion, ...]
    provider_name: str | None = None
    line_explanations: tuple[LessonLineExplanation, ...] = ()
    quiz_provider_name: str | None = None


@dataclass(frozen=True)
class ActiveLessonDraft:
    lesson_session_id: str
    content: LessonContent
    line_explanations: tuple[LessonLineExplanation, ...]
    provider_name: str


@dataclass(frozen=True)
class DueReviewItem:
    item: FixtureItem
    question: FixtureQuestion
    mastery_score: float
    dimension_scores: dict[str, float]
    next_review_at: datetime


@dataclass(frozen=True)
class ActiveReview:
    review_session_id: str
    items: tuple[DueReviewItem, ...]


@dataclass(frozen=True)
class AttemptResult:
    item_id: str
    question_id: str
    is_correct: bool
    outcome: ReviewOutcome
    mastery_score: float
    sm2_interval_days: int
    sm2_ease: float
    next_review_at: datetime | None
    duplicate: bool
    graded: bool = True


@dataclass(frozen=True)
class CompletionRecord:
    topic_id: str
    difficulty: str
    studied_item_ids: tuple[str, ...]
    completed_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class LessonService:
    """Persists compact evidence and progress; the pure policy computes the numbers."""

    POLICY = SM2MasteryPolicy()
    POLICY_VERSION = POLICY.version
    MASTERY_THRESHOLD = POLICY.MASTERY_THRESHOLD
    AGAIN_REVIEW_DELAY = POLICY.AGAIN_REVIEW_DELAY

    def __init__(
        self,
        engine: Engine,
        clock: Callable[[], datetime] = _utc_now,
        toolkit: LanguageToolkit | None = None,
    ) -> None:
        self._engine = engine
        self._clock = clock
        # With a toolkit, items from generated lessons keep their reference-list
        # name and become reviewable with code-built questions.
        self._toolkit = toolkit

    def now(self) -> datetime:
        return self._clock()

    def _reviewable(self):
        """SQL condition: an item the due review can build a question for."""

        if self._toolkit is None:
            return UserItemProgress.item_id.in_(REVIEW_QUESTIONS)
        return or_(
            UserItemProgress.item_id.in_(REVIEW_QUESTIONS),
            LearningItem.expression.is_not(None),
        )

    def start_fixture_lesson(
        self, user_id: int, lesson_session_id: str | None = None
    ) -> ActiveLesson:
        retries = tuple(RETRY_QUESTIONS[question.question_id] for question in FIXTURE_LESSON.questions)
        return self._start_lesson(
            user_id,
            FIXTURE_LESSON,
            retries,
            lesson_session_id=lesson_session_id,
        )

    def start_generated_lesson_draft(
        self, user_id: int, generated: object
    ) -> ActiveLessonDraft:
        if not isinstance(generated, GeneratedLessonDraft):
            raise LessonStateError("A validated generated lesson draft is required.")
        session_id = str(uuid4())
        self._record_exposure(user_id, generated.content.items)
        return ActiveLessonDraft(
            session_id,
            generated.content,
            generated.line_explanations,
            generated.provider_name,
        )

    def activate_generated_quiz(
        self, draft: ActiveLessonDraft, generated_quiz: object
    ) -> ActiveLesson:
        if not isinstance(generated_quiz, GeneratedQuiz):
            raise LessonStateError("A validated generated quiz is required.")
        content = draft.content
        lesson = FixtureLesson(
            topic_id=content.topic_id,
            title=content.title,
            difficulty=content.difficulty,
            passage=content.passage,
            items=content.items,
            questions=generated_quiz.questions,
            recap=content.recap,
        )
        return ActiveLesson(
            draft.lesson_session_id,
            lesson,
            generated_quiz.retry_questions,
            draft.provider_name,
            draft.line_explanations,
            generated_quiz.provider_name,
        )

    def _start_lesson(
        self,
        user_id: int,
        lesson: FixtureLesson,
        retry_questions: tuple[FixtureQuestion, ...],
        *,
        lesson_session_id: str | None = None,
        provider_name: str | None = None,
        line_explanations: tuple[LessonLineExplanation, ...] = (),
    ) -> ActiveLesson:
        session_id = lesson_session_id or str(uuid4())
        self._record_exposure(user_id, lesson.items)
        return ActiveLesson(
            session_id, lesson, retry_questions, provider_name, line_explanations
        )

    def _record_exposure(
        self, user_id: int, items: tuple[FixtureItem, ...]
    ) -> None:
        with Session(self._engine) as session:
            for fixture_item in items:
                self._ensure_item(session, fixture_item)
                progress = self._get_progress(
                    session, user_id, fixture_item.canonical_id
                )
                if progress is None:
                    progress = UserItemProgress(
                        user_id=user_id,
                        item_id=fixture_item.canonical_id,
                        exposure_count=1,
                    )
                    session.add(progress)
                else:
                    progress.exposure_count += 1
            session.commit()

    def get_due_count(self, user_id: int) -> int:
        with Session(self._engine) as session:
            count = session.scalar(
                select(func.count(UserItemProgress.id))
                .join(LearningItem, LearningItem.canonical_id == UserItemProgress.item_id)
                .where(
                    UserItemProgress.user_id == user_id,
                    self._reviewable(),
                    UserItemProgress.next_review_at.is_not(None),
                    UserItemProgress.next_review_at <= self._clock(),
                )
            )
            return int(count or 0)

    def get_next_review_at(self, user_id: int) -> datetime | None:
        with Session(self._engine) as session:
            return session.scalar(
                select(func.min(UserItemProgress.next_review_at)).where(
                    UserItemProgress.user_id == user_id,
                    UserItemProgress.next_review_at.is_not(None),
                )
            )

    def start_due_review(
        self, user_id: int, review_session_id: str | None = None
    ) -> ActiveReview:
        session_id = review_session_id or str(uuid4())
        with Session(self._engine) as session:
            rows = session.execute(
                select(UserItemProgress, LearningItem)
                .join(LearningItem, LearningItem.canonical_id == UserItemProgress.item_id)
                .where(
                    UserItemProgress.user_id == user_id,
                    self._reviewable(),
                    UserItemProgress.next_review_at.is_not(None),
                    UserItemProgress.next_review_at <= self._clock(),
                )
                .order_by(
                    UserItemProgress.next_review_at,
                    UserItemProgress.mastery_score,
                    UserItemProgress.item_id,
                )
                .limit(20)
            ).all()
            built = (self._due_review_item(progress, item) for progress, item in rows)
            review_items = tuple(item for item in built if item is not None)[:5]
        return ActiveReview(session_id, review_items)

    def submit_review_answer(
        self,
        user_id: int,
        review_session_id: str,
        question_id: str,
        selected_option_index: int,
        *,
        confidence: AnswerConfidence = AnswerConfidence.SURE,
        active_review: ActiveReview | None = None,
    ) -> AttemptResult:
        question = self._find_question(
            (
                question
                for candidates in REVIEW_QUESTIONS.values()
                for question in candidates
            ),
            question_id,
        )
        review_item = None
        if question is None and active_review is not None:
            if active_review.review_session_id != review_session_id:
                raise LessonStateError("This question is not part of the active review.")
            review_item = next(
                (entry for entry in active_review.items if entry.question.question_id == question_id),
                None,
            )
            question = review_item.question if review_item is not None else None
        if question is None:
            raise LessonStateError("This question is not part of the active review.")
        return self._submit_question(
            user_id,
            review_session_id,
            question,
            selected_option_index,
            is_retry=False,
            require_due=True,
            lesson_item=review_item.item if review_item is not None else None,
            confidence=confidence,
        )

    def submit_answer(
        self,
        user_id: int,
        lesson_session_id: str,
        question_id: str,
        selected_option_index: int,
        *,
        active_lesson: ActiveLesson | None = None,
        confidence: AnswerConfidence = AnswerConfidence.SURE,
    ) -> AttemptResult:
        active = active_lesson or self._fixture_active(lesson_session_id)
        self._require_session(active, lesson_session_id)
        question = self._find_question(active.lesson.questions, question_id)
        if question is None:
            raise LessonStateError("This question is not part of the active lesson.")
        lesson_item = next(
            item for item in active.lesson.items if item.canonical_id == question.item_id
        )
        return self._submit_question(
            user_id,
            lesson_session_id,
            question,
            selected_option_index,
            is_retry=False,
            lesson_item=lesson_item,
            confidence=confidence,
        )

    def submit_retry_answer(
        self,
        user_id: int,
        lesson_session_id: str,
        question_id: str,
        selected_option_index: int,
        *,
        active_lesson: ActiveLesson | None = None,
        confidence: AnswerConfidence = AnswerConfidence.SURE,
    ) -> AttemptResult:
        active = active_lesson or self._fixture_active(lesson_session_id)
        self._require_session(active, lesson_session_id)
        question = self._find_question(active.retry_questions, question_id)
        if question is None:
            raise LessonStateError("This retry is not part of the active lesson.")
        pending_ids = {
            retry.question_id
            for retry in self.get_pending_retries(
                user_id, lesson_session_id, active_lesson=active
            )
        }
        if question_id not in pending_ids:
            raise LessonStateError("This retry is not currently due.")
        lesson_item = next(
            item for item in active.lesson.items if item.canonical_id == question.item_id
        )
        return self._submit_question(
            user_id,
            lesson_session_id,
            question,
            selected_option_index,
            is_retry=True,
            lesson_item=lesson_item,
            confidence=confidence,
        )

    def _submit_question(
        self,
        user_id: int,
        lesson_session_id: str,
        question: FixtureQuestion,
        selected_option_index: int,
        *,
        is_retry: bool,
        require_due: bool = False,
        lesson_item: FixtureItem | None = None,
        confidence: AnswerConfidence = AnswerConfidence.SURE,
    ) -> AttemptResult:
        if selected_option_index not in range(len(question.options)):
            raise LessonStateError("Select one of the available answers.")

        now = self._clock()
        idempotency_key = sha256(
            f"{lesson_session_id}:{question.question_id}".encode("utf-8")
        ).hexdigest()
        with Session(self._engine) as session:
            existing = session.scalar(
                select(ReviewAttempt).where(
                    ReviewAttempt.user_id == user_id,
                    ReviewAttempt.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                progress = self._required_progress(session, user_id, existing.item_id)
                return self._attempt_result(existing, question.question_id, progress, True)

            fixture_item = lesson_item or next(
                item for item in REVIEW_ITEMS if item.canonical_id == question.item_id
            )
            self._ensure_item(session, fixture_item)
            progress = self._get_progress(session, user_id, question.item_id)
            if progress is None:
                progress = UserItemProgress(user_id=user_id, item_id=question.item_id)
                session.add(progress)
            elif require_due and (
                progress.next_review_at is None or progress.next_review_at > now
            ):
                raise LessonStateError("This item is not currently due for review.")

            if require_due:
                selected_question = self._select_review_question(progress, fixture_item)
                if selected_question is None or question.question_id != selected_question.question_id:
                    raise LessonStateError("This question is not part of the active review.")

            is_correct = selected_option_index == question.correct_option_index
            if not question.graded:
                # Practice only: log the answer, leave mastery and schedules untouched.
                attempt = ReviewAttempt(
                    user_id=user_id,
                    item_id=question.item_id,
                    lesson_session_id=lesson_session_id,
                    idempotency_key=idempotency_key,
                    question_form=question.form.value,
                    skill_dimension=skill_dimension(question.form, fixture_item.category).value,
                    answer_confidence=confidence.value,
                    is_correct=is_correct,
                    is_retry=is_retry,
                    is_graded=False,
                    outcome=(ReviewOutcome.GOOD if is_correct else ReviewOutcome.AGAIN).value,
                    policy_version="ungraded",
                    answered_at=now,
                )
                session.add(attempt)
                session.commit()
                session.refresh(progress)
                return self._attempt_result(attempt, question.question_id, progress, False)
            if is_correct:
                progress.correct_count += 1
            else:
                progress.incorrect_count += 1
            historical_attempts = session.scalars(
                select(ReviewAttempt).where(
                    ReviewAttempt.user_id == user_id,
                    ReviewAttempt.item_id == question.item_id,
                    ReviewAttempt.is_graded.is_(True),
                )
            ).all()
            dimension = skill_dimension(question.form, fixture_item.category)
            history = [
                PastAttempt(attempt.lesson_session_id, attempt.question_form, attempt.is_correct)
                for attempt in historical_attempts
            ]
            answer = Answer(
                question_form=question.form,
                skill_dimension=dimension,
                lesson_session_id=lesson_session_id,
                is_correct=is_correct,
                is_retry=is_retry,
                confidence=confidence,
                answered_at=now,
            )
            state = _item_state(progress)
            outcome = self.POLICY.outcome(state, history, answer)
            _write_item_state(progress, self.POLICY.apply(state, history, answer, outcome))
            progress.last_answered_at = now

            attempt = ReviewAttempt(
                user_id=user_id,
                item_id=question.item_id,
                lesson_session_id=lesson_session_id,
                idempotency_key=idempotency_key,
                question_form=question.form.value,
                skill_dimension=dimension.value,
                answer_confidence=confidence.value,
                is_correct=is_correct,
                is_retry=is_retry,
                outcome=outcome.value,
                policy_version=self.POLICY_VERSION,
                answered_at=now,
            )
            session.add(attempt)
            session.commit()
            session.refresh(progress)
            return self._attempt_result(attempt, question.question_id, progress, False)

    def get_pending_retries(
        self,
        user_id: int,
        lesson_session_id: str,
        *,
        active_lesson: ActiveLesson | None = None,
    ) -> tuple[FixtureQuestion, ...]:
        active = active_lesson or self._fixture_active(lesson_session_id)
        self._require_session(active, lesson_session_id)
        with Session(self._engine) as session:
            attempts = session.scalars(
                select(ReviewAttempt).where(
                    ReviewAttempt.user_id == user_id,
                    ReviewAttempt.lesson_session_id == lesson_session_id,
                )
            ).all()
        failed_item_ids = {
            attempt.item_id
            for attempt in attempts
            if not attempt.is_retry and not attempt.is_correct
        }
        retried_item_ids = {attempt.item_id for attempt in attempts if attempt.is_retry}
        return tuple(
            retry
            for question, retry in zip(
                active.lesson.questions, active.retry_questions, strict=True
            )
            if question.item_id in failed_item_ids
            and question.item_id not in retried_item_ids
        )

    @staticmethod
    def _fixture_active(lesson_session_id: str) -> ActiveLesson:
        retries = tuple(
            RETRY_QUESTIONS[question.question_id]
            for question in FIXTURE_LESSON.questions
        )
        return ActiveLesson(lesson_session_id, FIXTURE_LESSON, retries)

    @staticmethod
    def _require_session(active: ActiveLesson, lesson_session_id: str) -> None:
        if active.lesson_session_id != lesson_session_id:
            raise LessonStateError("This lesson session is no longer active.")

    def complete_fixture_lesson(
        self, user_id: int, lesson_session_id: str
    ) -> CompletionRecord:
        return self.complete_lesson(user_id, self._fixture_active(lesson_session_id))

    def complete_lesson(
        self, user_id: int, active_lesson: ActiveLesson
    ) -> CompletionRecord:
        lesson_session_id = active_lesson.lesson_session_id
        lesson = active_lesson.lesson
        now = self._clock()
        with Session(self._engine) as session:
            existing = session.scalar(
                select(CompletedLessonMetadata).where(
                    CompletedLessonMetadata.user_id == user_id,
                    CompletedLessonMetadata.lesson_session_id == lesson_session_id,
                )
            )
            if existing is not None:
                return self._completion_record(existing)
            attempt_count = session.scalar(
                select(func.count(ReviewAttempt.id)).where(
                    ReviewAttempt.user_id == user_id,
                    ReviewAttempt.lesson_session_id == lesson_session_id,
                    ReviewAttempt.is_retry.is_(False),
                )
            )
            if attempt_count != len(lesson.questions):
                raise LessonStateError("Answer every question before completing the lesson.")
            if self.get_pending_retries(
                user_id, lesson_session_id, active_lesson=active_lesson
            ):
                raise LessonStateError("Complete each corrective retry before finishing.")

            completion = CompletedLessonMetadata(
                user_id=user_id,
                lesson_session_id=lesson_session_id,
                topic_id=lesson.topic_id,
                difficulty=lesson.difficulty,
                studied_item_ids=[
                    item.canonical_id for item in lesson.items
                ],
                completed_at=now,
            )
            session.add(completion)
            session.commit()
            session.refresh(completion)
            return self._completion_record(completion)

    def get_progress(self, user_id: int) -> tuple[ProgressRecord, ...]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(UserItemProgress, LearningItem)
                .join(LearningItem, LearningItem.canonical_id == UserItemProgress.item_id)
                .where(UserItemProgress.user_id == user_id)
                .order_by(UserItemProgress.item_id)
            ).all()
            return tuple(
                ProgressRecord(
                    item_id=progress.item_id,
                    category=ItemCategory(item.category),
                    exposure_count=progress.exposure_count,
                    correct_count=progress.correct_count,
                    incorrect_count=progress.incorrect_count,
                    mastery_score=progress.mastery_score,
                    dimension_scores=dict(progress.dimension_scores),
                    consecutive_successful_reviews=progress.consecutive_successful_reviews,
                    sm2_interval_days=progress.sm2_interval_days,
                    sm2_ease=progress.sm2_ease,
                    last_outcome=(
                        ReviewOutcome(progress.last_outcome)
                        if progress.last_outcome is not None
                        else None
                    ),
                    last_answered_at=progress.last_answered_at,
                    next_review_at=progress.next_review_at,
                    expression=item.expression or _FIXTURE_NAMES.get(progress.item_id),
                )
                for progress, item in rows
            )

    def get_completions(self, user_id: int) -> tuple[CompletionRecord, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(CompletedLessonMetadata)
                .where(CompletedLessonMetadata.user_id == user_id)
                .order_by(CompletedLessonMetadata.completed_at.desc())
            ).all()
            return tuple(self._completion_record(row) for row in rows)

    def _due_review_item(
        self, progress: UserItemProgress, learning_item: LearningItem
    ) -> DueReviewItem | None:
        if progress.next_review_at is None:
            raise LessonStateError("A due review item must have a review date.")
        fixture_item = next(
            (item for item in REVIEW_ITEMS if item.canonical_id == learning_item.canonical_id),
            None,
        )
        if fixture_item is None:
            built = self._build_review(progress, learning_item)
            if built is None:
                return None
            fixture_item, question = built
        else:
            question = self._select_review_question(progress, fixture_item)
        return DueReviewItem(
            item=fixture_item,
            question=question,
            mastery_score=progress.mastery_score,
            dimension_scores=dict(progress.dimension_scores or {}),
            next_review_at=progress.next_review_at,
        )

    def _build_review(
        self, progress: UserItemProgress, learning_item: LearningItem
    ) -> tuple[FixtureItem, FixtureQuestion] | None:
        if self._toolkit is None or not learning_item.expression:
            return None
        return build_review(
            learning_item.canonical_id,
            ItemCategory(learning_item.category),
            learning_item.expression,
            dict(progress.dimension_scores or {}),
            self._toolkit,
        )

    def _select_review_question(
        self, progress: UserItemProgress, fixture_item: FixtureItem
    ) -> FixtureQuestion | None:
        if fixture_item.canonical_id not in REVIEW_QUESTIONS:
            if self._toolkit is None:
                return None
            built = build_review(
                fixture_item.canonical_id,
                fixture_item.category,
                fixture_item.expression,
                dict(progress.dimension_scores or {}),
                self._toolkit,
            )
            return built[1] if built is not None else None
        return min(
            REVIEW_QUESTIONS[fixture_item.canonical_id],
            key=lambda question: (
                progress.dimension_scores.get(
                    skill_dimension(question.form, fixture_item.category).value,
                    0.0,
                ),
                question.question_id,
            ),
        )

    def _reference_name(self, fixture_item: FixtureItem) -> str | None:
        """The reference-list spelling, so only dictionary text is ever stored."""

        if fixture_item.canonical_id in REVIEW_QUESTIONS:
            return fixture_item.expression
        if self._toolkit is None:
            return None
        if fixture_item.category is ItemCategory.GRAMMAR:
            point = self._toolkit.grammar_point(fixture_item.expression)
            if point is None or fixture_item.canonical_id != f"grammar:{point.id}":
                return None
            return point.display[:64]
        entry = self._toolkit.lookup(fixture_item.expression)
        return entry.lemma[:64] if entry is not None else None

    def _ensure_item(self, session: Session, fixture_item: FixtureItem) -> None:
        existing = session.get(LearningItem, fixture_item.canonical_id)
        if existing is None:
            session.add(
                LearningItem(
                    canonical_id=fixture_item.canonical_id,
                    category=fixture_item.category.value,
                    expression=self._reference_name(fixture_item),
                    jlpt_level=fixture_item.jlpt_level,
                    jlpt_provenance=fixture_item.jlpt_provenance,
                    jlpt_confidence=fixture_item.jlpt_confidence,
                )
            )
        elif existing.expression is None:
            existing.expression = self._reference_name(fixture_item)

    @staticmethod
    def _get_progress(
        session: Session, user_id: int, item_id: str
    ) -> UserItemProgress | None:
        return session.scalar(
            select(UserItemProgress).where(
                UserItemProgress.user_id == user_id,
                UserItemProgress.item_id == item_id,
            )
        )

    def _required_progress(
        self, session: Session, user_id: int, item_id: str
    ) -> UserItemProgress:
        progress = self._get_progress(session, user_id, item_id)
        if progress is None:
            raise LessonStateError("Progress for this answer is unavailable.")
        return progress

    @staticmethod
    def _find_question(
        questions: object, question_id: str
    ) -> FixtureQuestion | None:
        return next(
            (
                candidate
                for candidate in questions
                if isinstance(candidate, FixtureQuestion)
                and candidate.question_id == question_id
            ),
            None,
        )

    @staticmethod
    def _attempt_result(
        attempt: ReviewAttempt,
        question_id: str,
        progress: UserItemProgress,
        duplicate: bool,
    ) -> AttemptResult:
        if attempt.is_graded and progress.next_review_at is None:
            raise LessonStateError("The answer did not produce a review schedule.")
        return AttemptResult(
            item_id=attempt.item_id,
            question_id=question_id,
            is_correct=attempt.is_correct,
            outcome=ReviewOutcome(attempt.outcome),
            mastery_score=progress.mastery_score,
            sm2_interval_days=progress.sm2_interval_days,
            sm2_ease=progress.sm2_ease,
            next_review_at=progress.next_review_at,
            duplicate=duplicate,
            graded=attempt.is_graded is not False,
        )

    @staticmethod
    def _completion_record(completion: CompletedLessonMetadata) -> CompletionRecord:
        return CompletionRecord(
            topic_id=completion.topic_id,
            difficulty=completion.difficulty,
            studied_item_ids=tuple(completion.studied_item_ids),
            completed_at=completion.completed_at,
        )


def _item_state(progress: UserItemProgress) -> ItemState:
    defaults = ItemState()

    def value(name: str):
        current = getattr(progress, name)
        return getattr(defaults, name) if current is None else current

    return ItemState(
        mastery_score=value("mastery_score"),
        dimension_scores=dict(progress.dimension_scores or {}),
        consecutive_successful_reviews=value("consecutive_successful_reviews"),
        sm2_interval_days=value("sm2_interval_days"),
        sm2_ease=value("sm2_ease"),
        next_review_at=progress.next_review_at,
        last_outcome=progress.last_outcome,
    )


def _write_item_state(progress: UserItemProgress, state: ItemState) -> None:
    progress.mastery_score = state.mastery_score
    progress.dimension_scores = dict(state.dimension_scores)
    progress.consecutive_successful_reviews = state.consecutive_successful_reviews
    progress.sm2_interval_days = state.sm2_interval_days
    progress.sm2_ease = state.sm2_ease
    progress.next_review_at = state.next_review_at
    progress.last_outcome = state.last_outcome
