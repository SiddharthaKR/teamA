from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from japanese_workplace_tutor.auth import AuthenticationService
from japanese_workplace_tutor.database import create_database_engine
from japanese_workplace_tutor.core.progress import skill_dimension
from japanese_workplace_tutor.lesson import (
    FIXTURE_LESSON,
    REVIEW_ITEMS,
    REVIEW_QUESTIONS,
    RETRY_QUESTIONS,
    AnswerConfidence,
    FixtureQuestion,
    ItemCategory,
    LessonService,
    LessonStateError,
    QuestionForm,
    ReviewOutcome,
    SkillDimension,
    display_options,
)
from japanese_workplace_tutor.models import (
    Base,
    CompletedLessonMetadata,
    LearningItem,
    ReviewAttempt,
    UserItemProgress,
)
from japanese_workplace_tutor.settings import Settings


NOW = datetime(2026, 8, 31, 12, 0, 0)


def create_services(database_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    auth = AuthenticationService(engine)
    return auth, LessonService(engine, clock=lambda: NOW), engine


def seed_due_review_items(engine, user_id: int) -> None:
    with Session(engine) as session:
        for index, item in enumerate(REVIEW_ITEMS):
            session.add(
                LearningItem(
                    canonical_id=item.canonical_id,
                    category=item.category.value,
                    jlpt_level=item.jlpt_level,
                    jlpt_provenance=item.jlpt_provenance,
                    jlpt_confidence=item.jlpt_confidence,
                )
            )
            session.add(
                UserItemProgress(
                    user_id=user_id,
                    item_id=item.canonical_id,
                    mastery_score=0.1 + (index * 0.05),
                    dimension_scores={"reading": 0.8} if index == 0 else {},
                    next_review_at=NOW - timedelta(days=2 if index < 3 else 1),
                )
            )
        session.commit()


def test_due_review_selection_is_user_scoped_ordered_and_limited(
    tmp_path: Path,
) -> None:
    auth, lessons, engine = create_services(tmp_path / "lesson.db")
    alice = auth.register("Alice", "correct horse battery staple")
    bob = auth.register("Bob", "another secure password")
    seed_due_review_items(engine, alice.id)

    review = lessons.start_due_review(
        alice.id, "review-11111111-1111-1111-1111-111111111111"
    )

    assert lessons.get_due_count(alice.id) == 7
    assert lessons.get_due_count(bob.id) == 0
    assert len(review.items) == 5
    assert tuple(item.item.canonical_id for item in review.items) == tuple(
        item.canonical_id for item in REVIEW_ITEMS[:5]
    )
    assert review.items[0].question.form is QuestionForm.MEANING
    engine.dispose()


def test_review_start_is_a_noop_and_submission_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "lesson.db"
    auth, lessons, engine = create_services(database_path)
    user = auth.register("Alice", "correct horse battery staple")
    seed_due_review_items(engine, user.id)
    before = lessons.get_progress(user.id)
    review = lessons.start_due_review(
        user.id, "review-11111111-1111-1111-1111-111111111111"
    )
    assert lessons.get_progress(user.id) == before

    review_item = review.items[0]
    first = lessons.submit_review_answer(
        user.id,
        review.review_session_id,
        review_item.question.question_id,
        review_item.question.correct_option_index,
    )
    duplicate = lessons.submit_review_answer(
        user.id,
        review.review_session_id,
        review_item.question.question_id,
        review_item.question.correct_option_index + 1,
    )

    assert first.is_correct is True
    assert first.outcome is ReviewOutcome.GOOD
    assert duplicate == first.__class__(**{**first.__dict__, "duplicate": True})
    assert lessons.get_due_count(user.id) == 6
    with Session(engine) as session:
        assert session.scalar(select(func.count(ReviewAttempt.id))) == 1
    engine.dispose()

    _, restarted_lessons, restarted_engine = create_services(database_path)
    assert restarted_lessons.get_due_count(user.id) == 6
    with Session(restarted_engine) as session:
        assert session.scalar(select(func.count(ReviewAttempt.id))) == 1
    restarted_engine.dispose()


def test_exposure_does_not_raise_mastery_and_answers_are_idempotent(
    tmp_path: Path,
) -> None:
    auth, lessons, engine = create_services(tmp_path / "lesson.db")
    user = auth.register("Alice", "correct horse battery staple")

    active = lessons.start_fixture_lesson(user.id, "11111111-1111-1111-1111-111111111111")
    before = lessons.get_progress(user.id)
    assert len(before) == 5
    assert all(record.exposure_count == 1 for record in before)
    assert all(record.mastery_score == 0.0 for record in before)

    question = FIXTURE_LESSON.questions[0]
    first = lessons.submit_answer(
        user.id,
        active.lesson_session_id,
        question.question_id,
        question.correct_option_index,
    )
    duplicate = lessons.submit_answer(
        user.id,
        active.lesson_session_id,
        question.question_id,
        question.correct_option_index + 1,
    )

    assert first.is_correct is True
    assert first.outcome is ReviewOutcome.GOOD
    assert first.mastery_score == 0.18
    assert duplicate.is_correct is True
    assert duplicate.mastery_score == 0.18
    assert duplicate.duplicate is True
    lessons.start_fixture_lesson(user.id)
    reopened_progress = lessons.get_progress(user.id)
    assert all(record.exposure_count == 2 for record in reopened_progress)
    answered_item = next(
        record for record in reopened_progress if record.item_id == question.item_id
    )
    assert answered_item.mastery_score == 0.18
    with Session(engine) as session:
        assert session.scalar(select(func.count(ReviewAttempt.id))) == 1
    engine.dispose()


def test_again_and_varied_retry_preserve_compact_hard_recovery(
    tmp_path: Path,
) -> None:
    auth, lessons, engine = create_services(tmp_path / "lesson.db")
    user = auth.register("Alice", "correct horse battery staple")
    active = lessons.start_fixture_lesson(user.id, "11111111-1111-1111-1111-111111111111")
    question = FIXTURE_LESSON.questions[0]

    failed = lessons.submit_answer(
        user.id, active.lesson_session_id, question.question_id, 1
    )
    retry = lessons.get_pending_retries(user.id, active.lesson_session_id)[0]
    recovered = lessons.submit_retry_answer(
        user.id,
        active.lesson_session_id,
        retry.question_id,
        retry.correct_option_index,
    )

    assert failed.outcome is ReviewOutcome.AGAIN
    assert failed.mastery_score == 0.0
    assert failed.sm2_interval_days == 0
    assert failed.next_review_at == NOW.replace() + lessons.AGAIN_REVIEW_DELAY
    assert retry.item_id == question.item_id
    assert retry.form != question.form
    assert retry.prompt != question.prompt
    assert recovered.outcome is ReviewOutcome.HARD
    assert recovered.mastery_score == 0.08
    assert recovered.sm2_interval_days == 1
    assert recovered.sm2_ease == 2.15
    assert lessons.get_pending_retries(user.id, active.lesson_session_id) == ()

    with Session(engine) as session:
        attempts = session.scalars(select(ReviewAttempt).order_by(ReviewAttempt.id)).all()
        assert [(row.outcome, row.is_retry) for row in attempts] == [
            ("again", False),
            ("hard", True),
        ]
        assert attempts[0].question_form != attempts[1].question_form
        assert all(row.policy_version == "t05-v1" for row in attempts)
    engine.dispose()


def test_easy_requires_varied_success_across_separate_sessions(tmp_path: Path) -> None:
    auth, lessons, engine = create_services(tmp_path / "lesson.db")
    user = auth.register("Alice", "correct horse battery staple")
    question = FIXTURE_LESSON.questions[0]

    first = lessons.start_fixture_lesson(user.id, "11111111-1111-1111-1111-111111111111")
    lessons.submit_answer(user.id, first.lesson_session_id, question.question_id, 1)
    retry = lessons.get_pending_retries(user.id, first.lesson_session_id)[0]
    lessons.submit_retry_answer(
        user.id, first.lesson_session_id, retry.question_id, retry.correct_option_index
    )

    outcomes = []
    for session_number in range(2, 6):
        active = lessons.start_fixture_lesson(
            user.id, f"{session_number:08d}-1111-1111-1111-111111111111"
        )
        result = lessons.submit_answer(
            user.id,
            active.lesson_session_id,
            question.question_id,
            question.correct_option_index,
        )
        outcomes.append(result.outcome)

    assert outcomes == [
        ReviewOutcome.GOOD,
        ReviewOutcome.GOOD,
        ReviewOutcome.EASY,
        ReviewOutcome.EASY,
    ]
    progress = next(
        record for record in lessons.get_progress(user.id) if record.item_id == question.item_id
    )
    assert progress.mastery_score == 1.0
    assert progress.last_outcome is ReviewOutcome.EASY
    assert progress.consecutive_successful_reviews == 4
    assert set(progress.dimension_scores) == {"recognition", "contextual_use"}
    assert progress.sm2_interval_days == 73
    assert progress.sm2_ease == 2.55
    engine.dispose()


def test_mixed_answers_create_compact_progress_and_one_completion(
    tmp_path: Path,
) -> None:
    auth, lessons, engine = create_services(tmp_path / "lesson.db")
    user = auth.register("Alice", "correct horse battery staple")
    active = lessons.start_fixture_lesson(user.id)

    with pytest.raises(LessonStateError, match="Answer every question"):
        lessons.complete_fixture_lesson(user.id, active.lesson_session_id)
    assert lessons.get_completions(user.id) == ()

    for index, question in enumerate(FIXTURE_LESSON.questions):
        selected = question.correct_option_index if index % 2 == 0 else 3
        lessons.submit_answer(
            user.id, active.lesson_session_id, question.question_id, selected
        )
    for retry in lessons.get_pending_retries(user.id, active.lesson_session_id):
        lessons.submit_retry_answer(
            user.id,
            active.lesson_session_id,
            retry.question_id,
            retry.correct_option_index,
        )

    completion = lessons.complete_fixture_lesson(user.id, active.lesson_session_id)
    duplicate = lessons.complete_fixture_lesson(user.id, active.lesson_session_id)
    progress = lessons.get_progress(user.id)

    assert completion == duplicate
    assert completion.topic_id == FIXTURE_LESSON.topic_id
    assert completion.difficulty == FIXTURE_LESSON.difficulty
    assert completion.studied_item_ids == tuple(
        item.canonical_id for item in FIXTURE_LESSON.items
    )
    assert sum(record.correct_count for record in progress) == 5
    assert sum(record.incorrect_count for record in progress) == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count(ReviewAttempt.id))) == 7
        assert session.scalar(select(func.count(CompletedLessonMetadata.id))) == 1
    engine.dispose()

    _, restarted_lessons, restarted_engine = create_services(tmp_path / "lesson.db")
    assert restarted_lessons.get_completions(user.id) == (completion,)
    restarted_engine.dispose()


def test_progress_is_user_scoped_and_survives_engine_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "lesson.db"
    auth, lessons, engine = create_services(database_path)
    alice = auth.register("Alice", "correct horse battery staple")
    bob = auth.register("Bob", "another secure password")
    active = lessons.start_fixture_lesson(alice.id)
    question = FIXTURE_LESSON.questions[0]
    lessons.submit_answer(
        alice.id,
        active.lesson_session_id,
        question.question_id,
        question.correct_option_index,
    )
    assert lessons.get_progress(bob.id) == ()
    engine.dispose()

    _, restarted_lessons, restarted_engine = create_services(database_path)
    restored = restarted_lessons.get_progress(alice.id)
    assert len(restored) == 5
    assert sum(record.correct_count for record in restored) == 1
    assert restarted_lessons.get_completions(alice.id) == ()
    restarted_engine.dispose()


def test_database_excludes_replayable_fixture_content(tmp_path: Path) -> None:
    database_path = tmp_path / "lesson.db"
    auth, lessons, engine = create_services(database_path)
    user = auth.register("Alice", "correct horse battery staple")
    active = lessons.start_fixture_lesson(user.id)
    for question in FIXTURE_LESSON.questions:
        lessons.submit_answer(
            user.id,
            active.lesson_session_id,
            question.question_id,
            question.correct_option_index,
        )
    lessons.complete_fixture_lesson(user.id, active.lesson_session_id)
    with Session(engine) as session:
        for progress in session.scalars(select(UserItemProgress)).all():
            progress.next_review_at = NOW
        session.commit()
    review = lessons.start_due_review(user.id)
    for review_item in review.items:
        question = review_item.question
        lessons.submit_review_answer(
            user.id,
            review.review_session_id,
            question.question_id,
            question.correct_option_index,
        )
    engine.dispose()

    with sqlite3.connect(database_path) as connection:
        # Item names (one dictionary word or grammar point each) are stored on
        # purpose for the progress view; everything else stays out.
        item_names = {
            row[0]
            for row in connection.execute(
                "SELECT expression FROM learning_items WHERE expression IS NOT NULL"
            )
        }
        connection.execute("UPDATE learning_items SET expression = NULL")
        database_dump = "\n".join(connection.iterdump())
    assert item_names <= {item.expression for item in REVIEW_ITEMS}

    prohibited_content = [FIXTURE_LESSON.passage, FIXTURE_LESSON.recap]
    prohibited_content.extend(item.example for item in REVIEW_ITEMS)
    for questions in REVIEW_QUESTIONS.values():
        for question in questions:
            prohibited_content.extend((question.prompt, question.explanation))
            prohibited_content.extend(question.options)
    for question in FIXTURE_LESSON.questions:
        prohibited_content.extend((question.prompt, question.explanation))
        prohibited_content.extend(question.options)
    for retry in RETRY_QUESTIONS.values():
        prohibited_content.extend((retry.prompt, retry.explanation))
        prohibited_content.extend(retry.options)

    leaked_content = [
        content for content in prohibited_content if content in database_dump
    ]
    assert leaked_content == []


def test_display_options_are_stable_and_preserve_the_stored_option_set() -> None:
    for question in (*FIXTURE_LESSON.questions, *RETRY_QUESTIONS.values()):
        shuffled = display_options(question)
        assert shuffled == display_options(question)
        assert sorted(shuffled) == sorted(question.options)


def test_display_options_break_the_fixed_correct_answer_position() -> None:
    positions = {
        display_options(question).index(
            question.options[question.correct_option_index]
        )
        for question in (*FIXTURE_LESSON.questions, *RETRY_QUESTIONS.values())
    }
    assert positions != {0}


def test_duplicate_question_options_are_rejected() -> None:
    with pytest.raises(ValueError):
        FixtureQuestion(
            question_id="duplicate-options",
            item_id="vocabulary:shinchoku",
            form=QuestionForm.MEANING,
            prompt="What does 進捗 mean?",
            options=("Progress", "Progress", "Budget", "Agenda"),
            correct_option_index=0,
            explanation="進捗 describes how far work has progressed.",
        )


def test_a_guessed_correct_answer_earns_less_mastery(tmp_path: Path) -> None:
    question = FIXTURE_LESSON.questions[0]
    sure_path = tmp_path / "sure.db"
    guessed_path = tmp_path / "guessed.db"

    def answer(database_path: Path, confidence: AnswerConfidence) -> float:
        auth, lessons, engine = create_services(database_path)
        user = auth.register("Alice", "correct horse battery staple")
        active = lessons.start_fixture_lesson(user.id)
        lessons.submit_answer(
            user.id,
            active.lesson_session_id,
            question.question_id,
            question.correct_option_index,
            confidence=confidence,
        )
        mastery = next(
            record.mastery_score
            for record in lessons.get_progress(user.id)
            if record.item_id == question.item_id
        )
        engine.dispose()
        return mastery

    sure_mastery = answer(sure_path, AnswerConfidence.SURE)
    guessed_mastery = answer(guessed_path, AnswerConfidence.GUESSED)

    assert guessed_mastery < sure_mastery


def test_answer_confidence_is_stored_with_the_attempt(tmp_path: Path) -> None:
    database_path = tmp_path / "confidence.db"
    auth, lessons, engine = create_services(database_path)
    user = auth.register("Alice", "correct horse battery staple")
    active = lessons.start_fixture_lesson(user.id)
    question = FIXTURE_LESSON.questions[0]

    lessons.submit_answer(
        user.id,
        active.lesson_session_id,
        question.question_id,
        question.correct_option_index,
        confidence=AnswerConfidence.GUESSED,
    )

    with Session(engine) as session:
        stored = session.scalars(select(ReviewAttempt)).all()
    engine.dispose()

    assert [attempt.answer_confidence for attempt in stored] == ["guessed"]


def test_register_questions_score_as_contextual_use() -> None:
    question = FixtureQuestion(
        question_id="register-manager",
        item_id="vocabulary:shinchoku",
        form=QuestionForm.REGISTER,
        prompt="Speaking to your manager, which phrasing fits?",
        options=(
            "進捗を共有いたします",
            "進捗を共有するね",
            "進捗を共有だよ",
            "進捗を共有しとく",
        ),
        correct_option_index=0,
        explanation="The humble form suits a manager.",
    )

    assert (
        skill_dimension(question.form, ItemCategory.VOCABULARY)
        is SkillDimension.CONTEXTUAL_USE
    )