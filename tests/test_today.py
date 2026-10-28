from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from japanese_workplace_tutor.auth import AuthenticationService
from japanese_workplace_tutor.database import create_database_engine
from japanese_workplace_tutor.lesson import LessonService
from japanese_workplace_tutor.models import Base, CompletedLessonMetadata
from japanese_workplace_tutor.profile import JapaneseLevel, ProfileService
from japanese_workplace_tutor.settings import Settings
from japanese_workplace_tutor.today import TodayService, load_situation_steps
from japanese_workplace_tutor.today import tag_today_draft
from japanese_workplace_tutor.lesson import FIXTURE_LESSON
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit
from japanese_workplace_tutor.schemas.lessons import GeneratedLessonDraft


def test_catalog_has_distinct_steps_for_each_milestone() -> None:
    steps = load_situation_steps()
    assert len({step.id for step in steps}) == len(steps)
    assert {step.milestone_id for step in steps} == {"get-by", "take-part", "contribute"}
    assert all(step.title and (step.scenario or step.track in {"grammar", "sentence-order"})
               for step in steps)
    assert {step.track for step in steps} == {
        "situation", "words", "grammar", "sentence-order"
    }
    toolkit = SudachiToolkit.shared()
    for step in steps:
        if step.track == "words":
            assert step.words and all(
                (entry := toolkit.lookup(word)) is not None and entry.business_group
                for word in step.words
            )
        elif step.track == "grammar":
            assert step.grammar and toolkit.grammar_point(step.grammar)
        elif step.track == "sentence-order":
            assert step.answer and "".join(step.chunks) == step.answer
            assert len(set(step.chunks)) == len(step.chunks)
            assert (entry := toolkit.lookup(step.answer)) is not None and entry.business_group


def test_today_plan_uses_only_signed_in_users_profile_and_completions(tmp_path: Path) -> None:
    path = tmp_path / "today.db"
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path.as_posix()}",
                                             _env_file=None))
    Base.metadata.create_all(engine)
    auth = AuthenticationService(engine)
    profiles = ProfileService(engine)
    lessons = LessonService(engine)
    alice = auth.register("Alice", "correct horse battery staple")
    bob = auth.register("Bob", "another secure password")
    for user in (alice, bob):
        profiles.create_profile(user.id, role="Engineer", tasks=[],
                                declared_level=JapaneseLevel.N4,
                                milestone_id="take-part")
    first = next(step for step in load_situation_steps()
                 if step.milestone_id == "take-part")
    with Session(engine) as session:
        session.add(CompletedLessonMetadata(
            user_id=alice.id, lesson_session_id="s1", topic_id=first.topic_id,
            difficulty="JLPT N4", studied_item_ids=[],
            completed_at=datetime(2026, 11, 1),
        ))
        session.commit()

    today = TodayService(profiles, lessons)
    assert today.build_today_plan(alice.id).completed_steps == 1
    assert today.build_today_plan(alice.id).next_step != first
    assert today.build_today_plan(bob.id).completed_steps == 0
    assert today.build_today_plan(bob.id).next_step == first
    engine.dispose()


def test_today_route_is_recorded_only_for_its_generated_scenario() -> None:
    step = load_situation_steps()[0]
    draft = GeneratedLessonDraft(FIXTURE_LESSON, (), "Model")

    tagged = tag_today_draft(draft, step.topic_id, step.scenario,
                             step.scenario, mock_mode=False)
    assert tagged.content.topic_id == step.topic_id
    assert draft.content.topic_id != step.topic_id
    assert tag_today_draft(draft, step.topic_id, step.scenario,
                           "A different scenario", mock_mode=False) is draft
    assert tag_today_draft(draft, step.topic_id, step.scenario,
                           step.scenario, mock_mode=True) is draft


def test_local_grammar_and_order_routes_require_correct_answers_and_are_user_scoped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "practice.db"
    engine = create_database_engine(Settings(database_url=f"sqlite:///{path.as_posix()}",
                                             _env_file=None))
    Base.metadata.create_all(engine)
    auth = AuthenticationService(engine)
    profiles = ProfileService(engine)
    lessons = LessonService(engine)
    alice = auth.register("Alice", "correct horse battery staple")
    bob = auth.register("Bob", "another secure password")
    for user in (alice, bob):
        profiles.create_profile(user.id, role="Engineer", tasks=[],
                                declared_level=JapaneseLevel.N4, milestone_id="get-by")
    today = TodayService(profiles, lessons, SudachiToolkit.shared())
    grammar = next(step for step in load_situation_steps() if step.id == "get-by:grammar")
    order = next(step for step in load_situation_steps() if step.id == "get-by:order")

    assert not today.submit_practice(alice.id, grammar.topic_id, "〜ません")
    assert today.submit_practice(alice.id, grammar.topic_id, grammar.grammar)
    assert today.submit_practice(alice.id, grammar.topic_id, grammar.grammar)
    assert len([row for row in lessons.get_completions(alice.id)
                if row.topic_id == grammar.topic_id]) == 1
    assert today.build_today_plan(bob.id).completed_steps == 0
    assert not today.submit_practice(alice.id, order.topic_id, (1, 0, 2))
    assert today.submit_practice(alice.id, order.topic_id, (0, 1, 2))
    assert not today.submit_practice(alice.id, "path:get-by:words", "anything")
    engine.dispose()
