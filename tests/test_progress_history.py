"""Decision 15: progress over time, replayed from the stored answers."""

from datetime import date, datetime, timedelta
from pathlib import Path

from japanese_workplace_tutor.auth import AuthenticationService
from japanese_workplace_tutor.core.history import (
    answer_points,
    mastered_at,
    this_week,
    week_of,
    week_start,
    weekly_history,
)
from japanese_workplace_tutor.core.items import AnswerConfidence, ItemCategory, QuestionForm, SkillDimension
from japanese_workplace_tutor.core.progress import Answer
from japanese_workplace_tutor.database import create_database_engine
from japanese_workplace_tutor.features.lessons import canonical_item_id
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit
from japanese_workplace_tutor.lesson import FIXTURE_LESSON, LessonService
from japanese_workplace_tutor.models import Base
from japanese_workplace_tutor.progress_view import build_progress_history, load_milestones
from japanese_workplace_tutor.settings import Settings

TOOLKIT = SudachiToolkit.shared()
START = datetime(2026, 11, 2, 1, 0, 0)  # Monday 10:00 in Japan


def answer(day: float, form: QuestionForm, correct: bool = True, session: str | None = None) -> Answer:
    return Answer(
        question_form=form,
        skill_dimension=SkillDimension.RECOGNITION if form is QuestionForm.MEANING else SkillDimension.READING,
        lesson_session_id=session or f"s{day}",
        is_correct=correct,
        is_retry=False,
        confidence=AnswerConfidence.SURE,
        answered_at=START + timedelta(days=day),
    )


FASTEST_PATH = [
    answer(0, QuestionForm.MEANING),
    answer(1, QuestionForm.READING),
    answer(4, QuestionForm.MEANING),
    answer(19, QuestionForm.READING),
]


def test_weeks_start_monday_japan_time() -> None:
    sunday_night_utc = datetime(2026, 11, 1, 15, 30)  # Monday 00:30 in Japan
    assert week_of(sunday_night_utc) == date(2026, 11, 2)
    assert week_of(datetime(2026, 11, 1, 14, 30)) == date(2026, 10, 26)
    assert week_start(date(2026, 11, 2)) == datetime(2026, 11, 1, 15, 0)


def test_replay_matches_the_fastest_path_to_mastery() -> None:
    points = answer_points("vocabulary:x", FASTEST_PATH)
    assert [point.mastery_after for point in points] == [0.18, 0.36, 0.66, 0.96]
    assert [point.after_gap for point in points] == [False, True, True, True]


def test_weekly_history_counts_mastered_items_and_recall() -> None:
    points = {"vocabulary:x": answer_points("vocabulary:x", FASTEST_PATH)}
    now = START + timedelta(days=20)
    weeks = weekly_history(points, now)

    assert [week.week for week in weeks] == [date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16)]
    assert [week.mastered for week in weeks] == [0, 0, 1]
    assert [(week.recall_correct, week.recall_total) for week in weeks] == [(2, 2), (0, 0), (1, 1)]
    assert weeks[1].recall_rate is None
    assert mastered_at(points, START + timedelta(days=19)) == frozenset()
    assert mastered_at(points, START + timedelta(days=19, seconds=1)) == {"vocabulary:x"}


def test_this_week_counts_first_mastery_once() -> None:
    points = {"vocabulary:x": answer_points("vocabulary:x", [*FASTEST_PATH, answer(20, QuestionForm.MEANING)])}
    summary = this_week(points, START + timedelta(days=20, hours=1))
    assert summary.week == date(2026, 11, 16)
    assert summary.newly_mastered == 1
    assert summary.answers == 2
    assert (summary.recall_correct, summary.recall_total) == (2, 2)

    later = this_week(points, START + timedelta(days=28))
    assert later.newly_mastered == 0 and later.answers == 0 and later.recall_rate is None


def test_wrong_answers_lower_recall_and_drop_mastery() -> None:
    path = [*FASTEST_PATH, answer(30, QuestionForm.MEANING, correct=False)]
    points = {"vocabulary:x": answer_points("vocabulary:x", path)}
    assert points["vocabulary:x"][-1].mastery_after < 0.8
    week = weekly_history(points, START + timedelta(days=31))[-1]
    assert (week.mastered, week.recall_correct, week.recall_total) == (0, 0, 1)


def test_milestone_change_over_four_weeks() -> None:
    words = ("会議", "共有", "資料")
    answers = {
        canonical_item_id(ItemCategory.VOCABULARY, word, TOOLKIT): tuple(FASTEST_PATH) for word in words
    }
    history = build_progress_history(answers, START + timedelta(days=20), TOOLKIT, load_milestones())

    assert history.milestone_change["take-part"] > 0
    assert history.milestone_change["get-by"] == 0
    assert history.weeks[-1].mastered == 3


def test_stored_progress_equals_the_replayed_evidence(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'h.db').as_posix()}", _env_file=None)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    user = AuthenticationService(engine).register("Alice", "correct horse battery staple")
    clock = {"now": START}
    lessons = LessonService(engine, clock=lambda: clock["now"])
    for day in (0, 2):
        clock["now"] = START + timedelta(days=day)
        active = lessons.start_fixture_lesson(user.id)
        for question in FIXTURE_LESSON.questions:
            lessons.submit_answer(user.id, active.lesson_session_id, question.question_id, question.correct_option_index)

    replayed = {
        item_id: answer_points(item_id, answers)[-1].mastery_after
        for item_id, answers in lessons.get_graded_answers(user.id).items()
    }
    stored = {record.item_id: record.mastery_score for record in lessons.get_progress(user.id) if record.correct_count}
    assert replayed == stored
    engine.dispose()
