"""Decision 13 step 1: named items, status, coverage, milestones, and due reviews
for items from generated lessons (code-built questions)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from japanese_workplace_tutor.auth import AuthenticationService
from japanese_workplace_tutor.core.coverage import coverage
from japanese_workplace_tutor.core.items import ItemCategory, KeySource, QuestionForm, ReviewOutcome
from japanese_workplace_tutor.core.language import WordSet
from japanese_workplace_tutor.core.progress import ItemStatus, ProgressRecord, item_status
from japanese_workplace_tutor.database import create_database_engine
from japanese_workplace_tutor.features.lessons import canonical_item_id
from japanese_workplace_tutor.features.review_questions import build_review
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit
from japanese_workplace_tutor.lesson import LessonService
from japanese_workplace_tutor.models import Base
from japanese_workplace_tutor.progress_view import build_progress_view, load_milestones
from japanese_workplace_tutor.settings import Settings

from test_trust_layer import mock_draft

TOOLKIT = SudachiToolkit.shared()
NOW = datetime(2026, 11, 2, 9, 0, 0)


def record(**changes) -> ProgressRecord:
    values = dict(
        item_id="vocabulary:x",
        category=ItemCategory.VOCABULARY,
        exposure_count=1,
        correct_count=0,
        incorrect_count=0,
        mastery_score=0.0,
        dimension_scores={},
        consecutive_successful_reviews=0,
        sm2_interval_days=0,
        sm2_ease=2.5,
        last_outcome=None,
        last_answered_at=None,
        next_review_at=None,
    )
    values.update(changes)
    return ProgressRecord(**values)


def test_item_status_rules() -> None:
    assert item_status(record(), NOW) is ItemStatus.NEW
    assert item_status(record(last_outcome=ReviewOutcome.AGAIN), NOW) is ItemStatus.SLIPPING
    learning = record(last_outcome=ReviewOutcome.GOOD, mastery_score=0.36, sm2_interval_days=3, next_review_at=NOW)
    assert item_status(learning, NOW) is ItemStatus.LEARNING
    mastered = record(last_outcome=ReviewOutcome.EASY, mastery_score=0.96, sm2_interval_days=57, next_review_at=NOW + timedelta(days=5))
    assert item_status(mastered, NOW) is ItemStatus.MASTERED
    overdue = record(last_outcome=ReviewOutcome.EASY, mastery_score=0.96, sm2_interval_days=10, next_review_at=NOW - timedelta(days=6))
    assert item_status(overdue, NOW) is ItemStatus.SLIPPING


def test_coverage_counts_mastered_members() -> None:
    word_set = WordSet("demo", "Demo", "words", frozenset({"会議", "資料", "共有", "進捗"}))
    result = coverage(word_set, lambda lemma: lemma in {"会議", "共有"})
    assert (result.mastered, result.total, result.share) == (2, 4, 0.5)


def test_toolkit_word_sets_and_milestones_line_up() -> None:
    sets = {word_set.id: word_set for word_set in TOOLKIT.word_sets()}
    assert {"jlpt-N5", "jlpt-N4", "jlpt-N3", "jlpt-N2", "jlpt-N1"} <= set(sets)
    assert "会議" in sets["jlpt-N4"].members
    assert "共有" in sets["business-meetings"].members
    assert all(not member.startswith("grammar:") for member in sets["grammar-N4"].members)
    milestones = load_milestones()
    assert [milestone.id for milestone in milestones] == ["get-by", "take-part", "contribute"]
    for milestone in milestones:
        assert set(milestone.word_sets) <= set(sets), milestone.id
        assert milestone.coverage_target == 0.8
        assert set(milestone.tasks) == {"read", "write", "speak"}


def test_mastered_items_raise_coverage_and_milestone_progress() -> None:
    mastered = [
        record(
            item_id=canonical_item_id(ItemCategory.VOCABULARY, word, TOOLKIT),
            expression=word,
            last_outcome=ReviewOutcome.EASY,
            mastery_score=0.96,
            sm2_interval_days=57,
            next_review_at=NOW + timedelta(days=30),
        )
        for word in ("会議", "共有")
    ]
    view = build_progress_view(mastered, NOW, TOOLKIT, load_milestones())

    by_id = {part.set_id: part for part in view.coverage}
    assert by_id["jlpt-N4"].mastered == 1
    assert by_id["business-meetings"].mastered == 2
    take_part = next(item for item in view.milestones if item.milestone.id == "take-part")
    assert take_part.mastered == 2  # 会議 is in N4 words and Business: meetings, counted once
    assert not take_part.words_ready
    assert sorted(row.name for row in view.items) == ["会議", "共有"]
    assert view.status_counts[ItemStatus.MASTERED] == 2


@pytest.mark.parametrize(
    ("category", "expression"),
    [(ItemCategory.KANJI, "会議"), (ItemCategory.VOCABULARY, "共有"), (ItemCategory.VOCABULARY, "進捗"), (ItemCategory.GRAMMAR, "〜ておく")],
)
def test_review_questions_are_built_by_code_with_verified_keys(category, expression) -> None:
    item_id = canonical_item_id(category, expression, TOOLKIT)
    for scores in ({}, {"recognition": 0.9}):
        item, question = build_review(item_id, category, expression, scores, TOOLKIT)
        assert question.key_source is KeySource.DERIVED and question.graded
        assert len(set(question.options)) == 4
        correct = question.options[question.correct_option_index]
        if question.form is QuestionForm.READING:
            assert correct in TOOLKIT.readings(item.expression)
            assert not any(option in TOOLKIT.readings(item.expression) for option in question.options[1:])
        else:
            assert correct in item.meaning
        # Same inputs, same question: the check on submit can rebuild it.
        assert build_review(item_id, category, expression, scores, TOOLKIT)[1] == question


def test_review_asks_the_weaker_skill() -> None:
    item_id = canonical_item_id(ItemCategory.KANJI, "会議", TOOLKIT)
    _, fresh = build_review(item_id, ItemCategory.KANJI, "会議", {}, TOOLKIT)
    _, after_meaning = build_review(item_id, ItemCategory.KANJI, "会議", {"recognition": 0.5}, TOOLKIT)
    assert fresh.form is QuestionForm.MEANING
    assert after_meaning.form is QuestionForm.READING


def test_unknown_words_get_no_review_question() -> None:
    item_id = canonical_item_id(ItemCategory.VOCABULARY, "ほげほげ", TOOLKIT)
    assert build_review(item_id, ItemCategory.VOCABULARY, "ほげほげ", {}, TOOLKIT) is None


def test_generated_lesson_items_are_named_and_come_back_for_review(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'p.db').as_posix()}", _env_file=None)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    user = AuthenticationService(engine).register("Alice", "correct horse battery staple")
    clock = {"now": NOW}
    lessons = LessonService(engine, clock=lambda: clock["now"], toolkit=TOOLKIT)

    service, draft = mock_draft()
    active_draft = lessons.start_generated_lesson_draft(user.id, draft)
    active = lessons.activate_generated_quiz(active_draft, service.generate_quiz(draft.content))
    for question in active.lesson.questions:
        lessons.submit_answer(
            user.id, active.lesson_session_id, question.question_id,
            question.correct_option_index, active_lesson=active,
        )

    records = lessons.get_progress(user.id)
    named = {item.expression for item in records if item.expression}
    assert "会議" in named
    assert all(name is None or TOOLKIT.lookup(name) or TOOLKIT.grammar_point(name) for name in named)

    clock["now"] = NOW + timedelta(days=2)
    assert lessons.get_due_count(user.id) > 0
    review = lessons.start_due_review(user.id)
    assert review.items and all(entry.question.key_source is KeySource.DERIVED for entry in review.items)

    first = review.items[0]
    before = next(item for item in lessons.get_progress(user.id) if item.item_id == first.item.canonical_id)
    result = lessons.submit_review_answer(
        user.id, review.review_session_id, first.question.question_id,
        first.question.correct_option_index, active_review=review,
    )
    assert result.graded and result.is_correct
    after = next(item for item in lessons.get_progress(user.id) if item.item_id == first.item.canonical_id)
    assert after.mastery_score > before.mastery_score
    assert after.next_review_at > clock["now"]
    engine.dispose()


def test_without_a_toolkit_only_curated_items_are_reviewed(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'q.db').as_posix()}", _env_file=None)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    user = AuthenticationService(engine).register("Bob", "correct horse battery staple")
    lessons = LessonService(engine, clock=lambda: NOW)
    service, draft = mock_draft()
    lessons.start_generated_lesson_draft(user.id, draft)

    assert all(record.expression is None for record in lessons.get_progress(user.id))
    engine.dispose()
