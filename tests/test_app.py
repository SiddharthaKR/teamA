from concurrent.futures import Future
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from streamlit.testing.v1 import AppTest
from sqlalchemy import select
from sqlalchemy.orm import Session

from japanese_workplace_tutor.auth import AuthenticationService
from japanese_workplace_tutor.app import PAGE_RENDERERS, _furigana_html, _glossary
from japanese_workplace_tutor.database import create_database_engine
from japanese_workplace_tutor.generation import GeneratedQuiz
from japanese_workplace_tutor.lesson import (
    ActiveLesson,
    ActiveLessonDraft,
    FIXTURE_LESSON,
    LessonContent,
    LessonExplanationPoint,
    LessonLineExplanation,
    REVIEW_ITEMS,
    RETRY_QUESTIONS,
    LessonService,
)
from japanese_workplace_tutor.models import LearningItem, ReviewAttempt, UserItemProgress
from japanese_workplace_tutor.profile import JapaneseLevel, ProfileService
from japanese_workplace_tutor.settings import Settings, get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def prepare_database(monkeypatch, database_path: Path) -> None:
    monkeypatch.setenv("JLT_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    get_settings.cache_clear()


def create_completed_user(database_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    user = AuthenticationService(engine).register(
        "Alice", "correct horse battery staple"
    )
    ProfileService(engine).create_profile(
        user.id,
        role="Software engineer",
        tasks=["Discuss requirements", "Give status updates"],
        declared_level=JapaneseLevel.N4,
    )
    engine.dispose()
    return user


def seed_due_item(database_path: Path, user_id: int) -> None:
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    item = REVIEW_ITEMS[0]
    with Session(engine) as session:
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
                next_review_at=datetime(2026, 8, 31, 0, 0, 0),
            )
        )
        session.commit()
    engine.dispose()


def test_all_required_pages_are_registered() -> None:
    assert tuple(PAGE_RENDERERS) == ("Home", "Learn", "Presentation", "Translate", "Progress", "Profile")


def test_app_starts_without_model_configuration(monkeypatch, tmp_path: Path) -> None:
    prepare_database(monkeypatch, tmp_path / "app.db")
    for name in (
        "JLT_MODEL_BASE_URL",
        "JLT_MODEL_API_KEY",
        "JLT_PRIMARY_MODEL",
        "JLT_FALLBACK_MODEL",
    ):
        monkeypatch.setenv(name, "")

    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()

    assert not app.exception
    assert any(title.value == "Demo authentication" for title in app.title)
    assert not app.sidebar.radio
    assert any("Model features unavailable" in warning.value for warning in app.warning)
    assert any("Database: ready" in success.value for success in app.success)


def test_dummy_model_configuration_changes_status_without_provider_call(monkeypatch, tmp_path: Path) -> None:
    prepare_database(monkeypatch, tmp_path / "app.db")
    monkeypatch.setenv("JLT_MODEL_BASE_URL", "https://proxy.invalid/v1")
    monkeypatch.setenv("JLT_MODEL_API_KEY", "dummy-test-value")
    monkeypatch.setenv("JLT_PRIMARY_MODEL", "primary-test-model")
    monkeypatch.setenv("JLT_FALLBACK_MODEL", "fallback-test-model")
    get_settings.cache_clear()

    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()

    assert not app.exception
    assert any("Model features: configured" in success.value for success in app.success)


def test_each_page_opens_without_exception(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    user = create_completed_user(database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.run()

    for page_name in PAGE_RENDERERS:
        app.sidebar.radio[0].set_value(page_name).run()
        assert not app.exception
        assert any(title.value == page_name for title in app.title)


def test_home_due_review_can_be_skipped_then_completed(
    monkeypatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    user = create_completed_user(database_path)
    seed_due_item(database_path, user.id)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.run()

    assert app.button(key="start_due_review")
    assert app.button(key="continue_learning")
    app.button(key="start_due_review").click().run()
    active = app.session_state["active_due_review"]
    app.button(key="skip_due_review").click().run()

    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    with Session(engine) as session:
        unchanged = session.scalar(
            select(UserItemProgress).where(UserItemProgress.user_id == user.id)
        )
        assert unchanged is not None
        assert unchanged.next_review_at == datetime(2026, 8, 31, 0, 0, 0)
        assert session.scalars(select(ReviewAttempt)).all() == []

    app.button(key="start_due_review").click().run()
    active = app.session_state["active_due_review"]
    review_item = active.items[0]
    question = review_item.question
    app.radio(
        key=f"due_review_{active.review_session_id}_{question.question_id}"
    ).set_value(question.options[question.correct_option_index])
    app.button(
        key=f"submit_due_review_{active.review_session_id}_{question.question_id}"
    ).click().run()
    app.button(key="complete_due_review").click().run()

    assert "start_due_review" not in {button.key for button in app.button}
    assert app.button(key="continue_learning")
    assert any("Review complete: 1 of 1 correct" in value.value for value in app.success)
    with Session(engine) as session:
        assert len(session.scalars(select(ReviewAttempt)).all()) == 1
        updated = session.scalar(
            select(UserItemProgress).where(UserItemProgress.user_id == user.id)
        )
        assert updated is not None
        assert updated.next_review_at > datetime(2026, 8, 31, 0, 0, 0)
    engine.dispose()


def test_register_logout_and_login_flow(monkeypatch, tmp_path: Path) -> None:
    prepare_database(monkeypatch, tmp_path / "app.db")
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()

    app.text_input(key="registration_username").input("Alice")
    app.text_input(key="registration_password").input("correct horse battery staple")
    app.button(key="FormSubmitter:registration_form-Create account").click().run()

    assert any(title.value == "Set up your learner profile" for title in app.title)
    assert not app.sidebar.radio

    app.button(key="onboarding_1_submit").click().run()
    assert any(title.value == "Home" for title in app.title)
    assert app.session_state["authenticated_username"] == "Alice"
    assert any("Software engineer" in subheader.value for subheader in app.subheader)

    app.sidebar.button[0].click().run()
    assert any(title.value == "Demo authentication" for title in app.title)
    assert "authenticated_user_id" not in app.session_state

    app.text_input(key="sign_in_username").input("alice")
    app.text_input(key="sign_in_password").input("correct horse battery staple")
    app.button(key="FormSubmitter:sign_in_form-Sign in").click().run()

    assert any(title.value == "Home" for title in app.title)
    assert app.session_state["authenticated_username"] == "Alice"


def test_onboarding_validates_tasks_and_profile_can_be_edited(
    monkeypatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()

    app.text_input(key="registration_username").input("Alice")
    app.text_input(key="registration_password").input("correct horse battery staple")
    app.button(key="FormSubmitter:registration_form-Create account").click().run()

    app.multiselect(key="onboarding_1_tasks").set_value([])
    app.button(key="onboarding_1_submit").click().run()
    assert any("at least one typical task" in error.value for error in app.error)

    app.selectbox(key="onboarding_1_role").set_value("Researcher").run()
    app.multiselect(key="onboarding_1_tasks").set_value(
        ["Review applications", "Meet inventors"]
    )
    app.selectbox(key="onboarding_1_declared_level").set_value("JLPT N5")
    app.button(key="onboarding_1_submit").click().run()

    assert any(title.value == "Home" for title in app.title)
    assert any("Researcher" in subheader.value for subheader in app.subheader)

    app.sidebar.radio[0].set_value("Profile").run()
    app.selectbox(key="profile_1_declared_level").set_value("JLPT N3")
    app.text_area(key="profile_1_tools_domain").input("Intellectual property")
    app.button(key="profile_1_submit").click().run()

    assert any(success.value == "Profile saved." for success in app.success)
    stored = ProfileService(
        create_database_engine(
            Settings(
                database_url=f"sqlite:///{database_path.as_posix()}", _env_file=None
            )
        )
    ).get_profile(1)
    assert stored is not None
    assert stored.declared_level is JapaneseLevel.N3
    assert stored.tools_domain == "Intellectual property"


def test_fixture_lesson_can_be_answered_completed_and_viewed_in_progress(
    monkeypatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    user = create_completed_user(database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.run()

    app.sidebar.radio[0].set_value("Learn").run()
    app.button(key="start_fixture_lesson").click().run()
    active = app.session_state["active_lesson"]

    for question in FIXTURE_LESSON.questions:
        answer_key = (
            f"lesson_answer_{active.lesson_session_id}_{question.question_id}"
        )
        submit_key = f"submit_{active.lesson_session_id}_{question.question_id}"
        app.radio(key=answer_key).set_value(
            question.options[question.correct_option_index]
        )
        app.button(key=submit_key).click().run()

    app.button(key="complete_fixture_lesson").click().run()
    assert any("Lesson completed" in success.value for success in app.success)
    assert "active_lesson" not in app.session_state

    app.sidebar.radio[0].set_value("Progress").run(timeout=10)
    assert not app.exception
    assert app.dataframe
    assert [header.value for header in app.subheader] == ["Milestones", "Coverage", "Your items"]
    assert "進捗" in app.dataframe[-1].value["Item"].tolist()

    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    lessons = LessonService(engine)
    assert len(lessons.get_progress(user.id)) == 5
    assert sum(record.correct_count for record in lessons.get_progress(user.id)) == 5
    assert len(lessons.get_completions(user.id)) == 1
    engine.dispose()


def test_generated_lesson_displays_the_llm_provider(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    user = create_completed_user(database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    explanation_point = LessonExplanationPoint(
        expression="進捗",
        reading="しんちょく",
        meaning="work progress",
        explanation="A noun used when reporting how far work has advanced.",
    )
    app.session_state["active_lesson"] = ActiveLesson(
        "generated-session",
        FIXTURE_LESSON,
        tuple(
            RETRY_QUESTIONS[question.question_id]
            for question in FIXTURE_LESSON.questions
        ),
        "GPT-5 nano",
        (
            LessonLineExplanation(
                japanese_text="開発の進捗を共有します。",
                english_meaning="I will share the development progress.",
                kanji=(),
                vocabulary=(explanation_point,),
                grammar=(),
            ),
        ),
    )
    app.run()

    app.sidebar.radio[0].set_value("Learn").run()

    assert any(
        caption.value == "Lesson generated with GPT-5 nano"
        for caption in app.caption
    )
    assert any('lang="ja"' in markdown.value for markdown in app.markdown)
    assert any(
        "<ruby>進捗<rt>しんちょく</rt></ruby>" in markdown.value
        for markdown in app.markdown
    )
    assert any(
        "進捗" in markdown.value and "しんちょく" in markdown.value
        for markdown in app.markdown
    )


def test_generated_quiz_stays_hidden_until_go_to_quiz(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    user = create_completed_user(database_path)
    content = LessonContent(
        topic_id=FIXTURE_LESSON.topic_id,
        title=FIXTURE_LESSON.title,
        difficulty=FIXTURE_LESSON.difficulty,
        passage=FIXTURE_LESSON.passage,
        items=FIXTURE_LESSON.items,
        recap=FIXTURE_LESSON.recap,
    )
    draft = ActiveLessonDraft("draft-session", content, (), "GPT-5 nano")
    future: Future[GeneratedQuiz] = Future()
    future.set_result(
        GeneratedQuiz(
            FIXTURE_LESSON.questions,
            tuple(
                RETRY_QUESTIONS[question.question_id]
                for question in FIXTURE_LESSON.questions
            ),
            "Tsuzumi 2",
        )
    )
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.session_state["active_lesson_draft"] = draft
    app.session_state["quiz_generation_future"] = future
    app.run()

    app.sidebar.radio[0].set_value("Learn").run()

    assert app.button(key="go_to_quiz")
    assert not any(subheader.value == "Practice" for subheader in app.subheader)
    app.button(key="go_to_quiz").click().run()

    assert any(subheader.value == "Practice" for subheader in app.subheader)
    assert any(
        caption.value == "Quiz generated with Tsuzumi 2"
        for caption in app.caption
    )
    assert "active_lesson_draft" not in app.session_state


def test_incorrect_answer_shows_correction_and_requires_varied_retry(
    monkeypatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    user = create_completed_user(database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.run()

    app.sidebar.radio[0].set_value("Learn").run()
    app.button(key="start_fixture_lesson").click().run()
    active = app.session_state["active_lesson"]
    failed_question = FIXTURE_LESSON.questions[0]

    for question in FIXTURE_LESSON.questions:
        answer_key = f"lesson_answer_{active.lesson_session_id}_{question.question_id}"
        selected_index = (
            1
            if question.question_id == failed_question.question_id
            else question.correct_option_index
        )
        app.radio(key=answer_key).set_value(question.options[selected_index])
        app.button(
            key=f"submit_{active.lesson_session_id}_{question.question_id}"
        ).click().run()

    assert any("The correct answer is" in error.value for error in app.error)
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    retry = LessonService(engine).get_pending_retries(
        user.id, active.lesson_session_id
    )[0]
    engine.dispose()
    assert retry.item_id == failed_question.item_id
    assert retry.form != failed_question.form

    retry_key = f"lesson_retry_{active.lesson_session_id}_{retry.question_id}"
    app.radio(key=retry_key).set_value(retry.options[retry.correct_option_index])
    app.button(
        key=f"submit_retry_{active.lesson_session_id}_{retry.question_id}"
    ).click().run()

    assert any("This counts as Hard" in success.value for success in app.success)
    assert app.button(key="complete_fixture_lesson")


def test_rendered_options_are_shuffled_without_breaking_scoring(
    monkeypatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    user = create_completed_user(database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.run()

    app.sidebar.radio[0].set_value("Learn").run()
    app.button(key="start_fixture_lesson").click().run()
    active = app.session_state["active_lesson"]

    rendered_positions = set()
    for question in FIXTURE_LESSON.questions:
        answer_key = f"lesson_answer_{active.lesson_session_id}_{question.question_id}"
        rendered = tuple(app.radio(key=answer_key).options)
        assert sorted(rendered) == sorted(question.options)
        rendered_positions.add(
            rendered.index(question.options[question.correct_option_index])
        )

    assert rendered_positions != {0}

    question = FIXTURE_LESSON.questions[0]
    answer_key = f"lesson_answer_{active.lesson_session_id}_{question.question_id}"
    app.radio(key=answer_key).set_value(
        question.options[question.correct_option_index]
    )
    app.button(
        key=f"submit_{active.lesson_session_id}_{question.question_id}"
    ).click().run()

    assert app.session_state["lesson_answer_results"][question.question_id] is True


def test_furigana_escapes_model_supplied_html_and_builds_ruby() -> None:
    point = LessonExplanationPoint(
        expression="進捗",
        reading="しんちょく",
        meaning="work progress",
        explanation="Reporting how far work has advanced.",
    )

    markup = _furigana_html("開発の進捗<script>alert(1)</script>", (point,))

    assert "<ruby>進捗<rt>しんちょく</rt></ruby>" in markup
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup


def test_furigana_escapes_a_malicious_reading() -> None:
    point = LessonExplanationPoint(
        expression="進捗",
        reading='"><img src=x onerror=alert(1)>',
        meaning="work progress",
        explanation="Reporting how far work has advanced.",
    )

    markup = _furigana_html("進捗", (point,))

    assert "<img" not in markup
    assert "&lt;img" in markup


def test_glossary_collapses_repeated_expressions() -> None:
    point = LessonExplanationPoint(
        expression="確認",
        reading="かくにん",
        meaning="confirmation",
        explanation="Used when checking something.",
    )
    lines = tuple(
        LessonLineExplanation(
            japanese_text=f"確認します。{number}",
            english_meaning="I will check.",
            kanji=(),
            vocabulary=(point,),
            grammar=(),
        )
        for number in range(1, 4)
    )

    glossary = _glossary(lines)

    assert len(glossary) == 1
    label, entry, line_numbers = glossary[0]
    assert (label, entry.expression) == ("Vocabulary", "確認")
    assert line_numbers == [1, 2, 3]


def test_mock_mode_generates_a_lesson_offline(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    for name in ("JLT_MODEL_BASE_URL", "JLT_MODEL_API_KEY", "JLT_PRIMARY_MODEL", "JLT_FALLBACK_MODEL"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("JLT_LLM_MODE", "mock")
    monkeypatch.setenv("JLT_MOCK_FIXTURE_DIR", str(PROJECT_ROOT / "fixtures" / "llm"))
    get_settings.cache_clear()
    user = create_completed_user(database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.run()

    assert any("mock mode" in info.value for info in app.info)
    app.sidebar.radio[0].set_value("Learn").run()
    app.button(key="generate_scenario_lesson").click().run()

    assert not app.exception
    assert any(
        caption.value == "Lesson generated with Mock (offline fixtures)"
        for caption in app.caption
    )
    get_settings.cache_clear()


def _signed_in_mock_app(monkeypatch, tmp_path: Path) -> AppTest:
    database_path = tmp_path / "app.db"
    prepare_database(monkeypatch, database_path)
    for name in ("JLT_MODEL_BASE_URL", "JLT_MODEL_API_KEY", "JLT_PRIMARY_MODEL", "JLT_FALLBACK_MODEL"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("JLT_LLM_MODE", "mock")
    monkeypatch.setenv("JLT_MOCK_FIXTURE_DIR", str(PROJECT_ROOT / "fixtures" / "llm"))
    get_settings.cache_clear()
    user = create_completed_user(database_path)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.session_state["authenticated_user_id"] = user.id
    app.session_state["authenticated_username"] = user.username
    app.run()
    return app


def test_typed_scenario_needs_public_content_confirmation(monkeypatch, tmp_path: Path) -> None:
    app = _signed_in_mock_app(monkeypatch, tmp_path)
    app.sidebar.radio[0].set_value("Learn").run()

    app.text_area(key="lesson_scenario").input("Ask my manager to move the meeting").run()
    assert app.button(key="generate_scenario_lesson").disabled
    assert any("Do not enter or upload work data" in warning.value for warning in app.warning)

    app.checkbox(key="scenario_public_ok").check().run()
    assert not app.button(key="generate_scenario_lesson").disabled
    get_settings.cache_clear()


def test_deck_localizer_needs_public_content_confirmation(monkeypatch, tmp_path: Path) -> None:
    app = _signed_in_mock_app(monkeypatch, tmp_path)
    app.sidebar.radio[0].set_value("Presentation").run()

    assert app.button(key="localize_deck").disabled
    app.checkbox(key="deck_public_ok").check().run()
    assert not app.button(key="localize_deck").disabled
    get_settings.cache_clear()


def test_reviewer_mode_adds_accuracy_page(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JLT_REVIEWER_MODE", "true")
    app = _signed_in_mock_app(monkeypatch, tmp_path)

    assert "Accuracy" in app.sidebar.radio[0].options
    app.sidebar.radio[0].set_value("Accuracy").run()
    assert not app.exception
    assert any("No reviews yet" in info.value for info in app.info)
    get_settings.cache_clear()


def test_reviewer_panel_records_verdicts_for_a_generated_lesson(monkeypatch, tmp_path: Path) -> None:
    from japanese_workplace_tutor.generation import LessonGenerationService, ScenarioMode
    from japanese_workplace_tutor.llm.mock import MockTransport
    from japanese_workplace_tutor.review import ReviewService

    monkeypatch.setenv("JLT_REVIEWER_MODE", "true")
    app = _signed_in_mock_app(monkeypatch, tmp_path)
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.db').as_posix()}", _env_file=None)
    engine = create_database_engine(settings)
    lessons = LessonService(engine)
    generation = LessonGenerationService(
        MockTransport(PROJECT_ROOT / "fixtures" / "llm"), "mock-primary", "mock-fallback"
    )
    user_id = app.session_state["authenticated_user_id"]
    profile = ProfileService(engine).get_profile(user_id)
    draft = generation.generate_lesson_content("", ScenarioMode.GENERATE, profile)
    active = lessons.activate_generated_quiz(
        lessons.start_generated_lesson_draft(user_id, draft), generation.generate_quiz(draft.content)
    )
    app.session_state["active_lesson"] = active
    app.sidebar.radio[0].set_value("Learn").run()

    assert not app.exception
    first_question = active.lesson.questions[0].question_id
    key = f"review_{active.lesson_session_id}_question_{first_question}"
    app.radio(key=key).set_value("Wrong").run()
    app.button(key=f"save_review_{active.lesson_session_id}").click().run()

    assert not app.exception
    assert ReviewService(engine).report().wrong == 1
    engine.dispose()
    get_settings.cache_clear()
