"""Streamlit application with persistent local demo authentication."""

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from html import escape
from pathlib import Path

import streamlit as st
from sqlalchemy import Engine

from .auth import AuthenticationError, AuthenticationService, RegistrationError
from .database import check_database, create_database_engine
from .generation import (
    GenerationError,
    GeneratedQuiz,
    LessonGenerationService,
    OpenAICompatibleTransport,
    ScenarioMode,
    detect_scenario_mode,
)
from .lesson import (
    ActiveLesson,
    ActiveLessonDraft,
    ActiveReview,
    AnswerConfidence,
    FIXTURE_LESSON,
    LessonExplanationPoint,
    LessonLineExplanation,
    LessonService,
    LessonStateError,
    ProgressRecord,
    QuestionForm,
    display_options,
)
from .profile import (
    JapaneseLevel,
    ProfileRecord,
    ProfileService,
    ProfileValidationError,
    ROLE_TASK_SUGGESTIONS,
)
from .settings import Settings, get_settings

PageRenderer = Callable[[], None]

JAPANESE_STYLE = """
<style>
.jp-line { font-size: 1.35rem; line-height: 2.2; margin: 0.15rem 0 0.4rem 0;
           font-family: "Yu Gothic", "Meiryo", "Noto Sans JP", "Hiragino Kaku Gothic ProN",
           sans-serif; }
.jp-line rt { font-size: 0.5em; opacity: 0.75; font-weight: 400; }
.jp-speaker { font-weight: 600; opacity: 0.7; margin-right: 0.4rem; }
</style>
"""


def _furigana_html(japanese_text: str, points: Sequence[LessonExplanationPoint]) -> str:
    """Wrap known kanji expressions in ruby tags, escaping all model text first."""

    rubies = sorted(
        (
            (point.expression, point.reading)
            for point in points
            if point.expression and point.reading
            and any("\u3400" <= character <= "\u9fff" for character in point.expression)
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    pieces: list[str] = []
    index = 0
    while index < len(japanese_text):
        for expression, reading in rubies:
            if japanese_text.startswith(expression, index):
                pieces.append(
                    f"<ruby>{escape(expression)}<rt>{escape(reading)}</rt></ruby>"
                )
                index += len(expression)
                break
        else:
            pieces.append(escape(japanese_text[index]))
            index += 1
    return "".join(pieces)


def _render_japanese_line(
    japanese_text: str,
    points: Sequence[LessonExplanationPoint],
    show_furigana: bool,
) -> None:
    speaker, separator, spoken = japanese_text.partition(": ")
    if not separator:
        speaker, spoken = "", japanese_text
    body = (
        _furigana_html(spoken, points) if show_furigana else escape(spoken)
    )
    prefix = f'<span class="jp-speaker">{escape(speaker)}</span>' if speaker else ""
    st.markdown(
        f'<div class="jp-line" lang="ja">{prefix}{body}</div>',
        unsafe_allow_html=True,
    )


def _line_points(line: LessonLineExplanation) -> tuple[LessonExplanationPoint, ...]:
    return (*line.kanji, *line.vocabulary, *line.grammar)


def _confidence_input(key: str, disabled: bool) -> AnswerConfidence:
    choice = st.radio(
        "How sure are you?",
        ("I am sure", "I guessed"),
        index=0,
        key=key,
        horizontal=True,
        disabled=disabled,
    )
    return (
        AnswerConfidence.GUESSED if choice == "I guessed" else AnswerConfidence.SURE
    )


def _glossary(
    line_explanations: Sequence[LessonLineExplanation],
) -> list[tuple[str, LessonExplanationPoint, list[int]]]:
    """Collapse repeated expressions into one entry listing the lines they appear on."""

    entries: dict[tuple[str, str], tuple[str, LessonExplanationPoint, list[int]]] = {}
    for number, line in enumerate(line_explanations, start=1):
        for label, points in (
            ("Kanji", line.kanji),
            ("Vocabulary", line.vocabulary),
            ("Grammar", line.grammar),
        ):
            for point in points:
                key = (label, point.expression)
                if key not in entries:
                    entries[key] = (label, point, [])
                entries[key][2].append(number)
    return list(entries.values())


@st.cache_resource
def _quiz_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="quiz-generation")


@st.cache_resource
def _generation_service(
    base_url: str,
    _api_key: str,
    primary_model: str,
    fallback_model: str,
    timeout_seconds: float,
    primary_timeout_seconds: float,
    hedge_after_seconds: float | None,
    parallel_explanations: bool,
    explanation_workers: int,
    quiz_primary_model: str,
    quiz_fallback_model: str,
) -> LessonGenerationService:
    return LessonGenerationService(
        OpenAICompatibleTransport(base_url, _api_key, timeout_seconds),
        primary_model,
        fallback_model,
        primary_timeout_seconds=primary_timeout_seconds,
        hedge_after_seconds=hedge_after_seconds,
        parallel_explanations=parallel_explanations,
        explanation_workers=explanation_workers,
        quiz_primary_model=quiz_primary_model,
        quiz_fallback_model=quiz_fallback_model,
    )


def _start_quiz_generation(
    generation_service: LessonGenerationService,
    draft: ActiveLessonDraft,
    learning_history: tuple[ProgressRecord, ...],
) -> Future[GeneratedQuiz]:
    return _quiz_executor().submit(
        generation_service.generate_quiz,
        draft.content,
        learning_history,
    )


def _clear_active_review() -> None:
    for key in list(st.session_state):
        if key in {"active_due_review", "due_review_results"} or key.startswith(
            "due_review_"
        ):
            st.session_state.pop(key, None)


def _continue_learning() -> None:
    _clear_active_review()
    st.session_state.navigation = "Learn"


def _render_due_review(
    service: LessonService, user_id: int, active: ActiveReview
) -> None:
    st.subheader("Review due items")
    st.caption(f"{len(active.items)} item{'s' if len(active.items) != 1 else ''} in this review")
    results = st.session_state.setdefault("due_review_results", {})

    for number, review_item in enumerate(active.items, start=1):
        question = review_item.question
        st.markdown(
            f"**{number}. {review_item.item.expression} · "
            f"{review_item.item.category.value}**"
        )
        st.write(question.prompt)
        st.caption(question.form.value.replace("_", " ").title())
        answer_key = (
            f"due_review_{active.review_session_id}_{question.question_id}"
        )
        selected_answer = st.radio(
            f"Answer for review item {number}",
            display_options(question),
            index=None,
            key=answer_key,
            label_visibility="collapsed",
            disabled=question.question_id in results,
        )
        confidence = _confidence_input(
            f"due_review_confidence_{active.review_session_id}_{question.question_id}",
            question.question_id in results,
        )
        if question.question_id in results:
            result = results[question.question_id]
            if result.is_correct:
                st.success(f"Correct. Outcome: {result.outcome.value.title()}.")
            else:
                correct_answer = question.options[question.correct_option_index]
                st.error(f"Not quite. The correct answer is {correct_answer}.")
            st.write(question.explanation)
            st.caption(
                "Next review: "
                + result.next_review_at.isoformat(sep=" ", timespec="minutes")
            )
        elif st.button(
            "Submit answer",
            key=(
                f"submit_due_review_{active.review_session_id}_"
                f"{question.question_id}"
            ),
        ):
            if selected_answer is None:
                st.warning("Choose an answer before submitting.")
            else:
                results[question.question_id] = service.submit_review_answer(
                    user_id,
                    active.review_session_id,
                    question.question_id,
                    question.options.index(selected_answer),
                    confidence=confidence,
                )
                st.rerun()

    if active.items and len(results) == len(active.items):
        if st.button("Complete review", type="primary", key="complete_due_review"):
            st.session_state.last_review_summary = {
                "correct": sum(result.is_correct for result in results.values()),
                "total": len(active.items),
                "next_review_at": service.get_next_review_at(user_id),
            }
            _clear_active_review()
            st.rerun()

    st.button("Start a lesson", key="continue_learning", on_click=_continue_learning)
    if st.button("Skip review", key="skip_due_review"):
        _clear_active_review()
        st.rerun()


def render_home(
    profile: ProfileRecord | None = None,
    service: LessonService | None = None,
    user_id: int | None = None,
) -> None:
    st.title("Home")
    username = st.session_state.get("authenticated_username")
    st.write(f"Welcome, {username}.")
    if profile is None:
        st.info("Complete your learner profile to personalize your learning.")
        return
    st.subheader(f"{profile.role} · {profile.declared_level.value}")
    st.write("Focus tasks: " + ", ".join(profile.tasks))
    if profile.tools_domain:
        st.caption(f"Tools and domain: {profile.tools_domain}")
    if service is None or user_id is None:
        st.info("A deterministic workplace status-update lesson is ready on Learn.")
        return

    active_review = st.session_state.get("active_due_review")
    if isinstance(active_review, ActiveReview):
        _render_due_review(service, user_id, active_review)
        return

    summary = st.session_state.get("last_review_summary")
    if isinstance(summary, dict):
        st.success(
            f"Review complete: {summary['correct']} of {summary['total']} correct."
        )
        next_review_at = summary.get("next_review_at")
        if next_review_at is not None:
            st.caption(
                "Earliest review: "
                + next_review_at.isoformat(sep=" ", timespec="minutes")
            )

    due_count = service.get_due_count(user_id)
    if due_count:
        st.subheader(f"{due_count} item{'s' if due_count != 1 else ''} due")
        st.write("A short review is ready. You can skip it and keep learning.")
        if st.button("Review due items", type="primary", key="start_due_review"):
            st.session_state.pop("last_review_summary", None)
            st.session_state.active_due_review = service.start_due_review(user_id)
            st.session_state.due_review_results = {}
            st.rerun()
        st.button(
            "Start a lesson", key="continue_learning", on_click=_continue_learning
        )
    else:
        st.write("No reviews are due. Continue with the workplace status-update lesson.")
        st.button(
            "Continue learning",
            type="primary",
            key="continue_learning",
            on_click=_continue_learning,
        )


def _clear_active_lesson() -> None:
    future = st.session_state.get("quiz_generation_future")
    if isinstance(future, Future):
        future.cancel()
    for key in list(st.session_state):
        if key in {
            "active_fixture_lesson",
            "active_lesson",
            "active_lesson_draft",
            "lesson_answer_results",
            "lesson_retry_results",
            "lesson_fallback_notice",
            "quiz_generation_future",
            "quiz_generation_error",
        } or key.startswith(("lesson_answer_", "lesson_retry_")):
            st.session_state.pop(key, None)


def render_learn(
    service: LessonService | None = None,
    user_id: int | None = None,
    profile: ProfileRecord | None = None,
    generation_service: LessonGenerationService | None = None,
) -> None:
    st.title("Learn")
    if service is None or user_id is None:
        st.info("Sign in to start a lesson.")
        return

    if "last_lesson_completion" in st.session_state:
        st.success("Lesson completed. Your compact progress and review schedule were saved.")
        st.session_state.pop("last_lesson_completion", None)

    active = st.session_state.get("active_lesson")
    draft = st.session_state.get("active_lesson_draft")
    if not isinstance(active, ActiveLesson) and not isinstance(draft, ActiveLessonDraft):
        st.subheader("Create a scenario lesson")
        scenario = st.text_area(
            "Workplace situation, goal, or Japanese text",
            max_chars=4000,
            key="lesson_scenario",
            placeholder="For example: I need to clarify a requirement with my manager.",
        )
        detected_mode = detect_scenario_mode(scenario) if scenario.strip() else ScenarioMode.GENERATE
        mode_options = [mode.value for mode in ScenarioMode]
        selected_mode = st.radio(
            "Lesson mode",
            mode_options,
            index=mode_options.index(detected_mode.value),
            key=f"scenario_mode_{detected_mode.name.lower()}",
            horizontal=True,
        )
        st.caption(f"Detected/default mode: {detected_mode.value}. Confirm or change it above.")
        generation_disabled = generation_service is None or profile is None
        if generation_disabled:
            st.info("Scenario generation is unavailable until model configuration is complete.")
        if st.button(
            "Generate lesson",
            type="primary",
            key="generate_scenario_lesson",
            disabled=generation_disabled,
        ) and generation_service is not None and profile is not None:
            try:
                learning_history = service.get_progress(user_id)
                generated = generation_service.generate_lesson_content(
                    scenario,
                    ScenarioMode(selected_mode),
                    profile,
                    learning_history=learning_history,
                    recent_topic_ids=tuple(
                        completion.topic_id
                        for completion in service.get_completions(user_id)[:10]
                    ),
                )
            except GenerationError as error:
                # Always-ship fallback: never dead-end the demo. If every model and
                # repair attempt fails, load the ready-made fixture lesson so the
                # learner can still complete the full loop, with an honest notice.
                _clear_active_lesson()
                st.session_state.active_lesson = service.start_fixture_lesson(user_id)
                st.session_state.lesson_answer_results = {}
                st.session_state.lesson_retry_results = {}
                st.session_state.lesson_fallback_notice = (
                    "Live lesson generation is temporarily unavailable, so we loaded a "
                    "ready-made sample lesson so you can keep learning. Please try "
                    f"generating again in a moment. (Reason: {error})"
                )
                st.rerun()
            else:
                _clear_active_lesson()
                active_draft = service.start_generated_lesson_draft(
                    user_id, generated
                )
                st.session_state.active_lesson_draft = active_draft
                st.session_state.quiz_generation_future = _start_quiz_generation(
                    generation_service,
                    active_draft,
                    tuple(learning_history),
                )
                st.session_state.lesson_answer_results = {}
                st.session_state.lesson_retry_results = {}
                st.rerun()

        st.divider()
        st.subheader(FIXTURE_LESSON.title)
        st.write("Study five workplace Japanese targets, then answer five questions.")
        st.caption("Opening the lesson records exposure only. It does not raise mastery.")
        if st.button("Start fixture lesson", key="start_fixture_lesson"):
            _clear_active_lesson()
            st.session_state.active_lesson = service.start_fixture_lesson(
                user_id
            )
            st.session_state.lesson_answer_results = {}
            st.session_state.lesson_retry_results = {}
            st.rerun()
        return

    if isinstance(active, ActiveLesson):
        lesson = active.lesson
        line_explanations = active.line_explanations
        provider_name = active.provider_name
    else:
        lesson = draft.content
        line_explanations = draft.line_explanations
        provider_name = draft.provider_name
    fallback_notice = st.session_state.get("lesson_fallback_notice")
    if isinstance(fallback_notice, str):
        st.warning(fallback_notice)
    st.subheader(lesson.title)
    st.caption(f"Difficulty: {lesson.difficulty}")
    if provider_name is not None:
        st.caption(f"Lesson generated with {provider_name}")

    target_expressions = {item.expression for item in lesson.items}
    points_by_line = {
        line.japanese_text: _line_points(line) for line in line_explanations
    }
    furigana_column, english_column = st.columns(2)
    show_furigana = furigana_column.toggle("Furigana", value=True, key="show_furigana")
    show_english = english_column.toggle(
        "Show English", value=False, key="show_english"
    )

    conversation_tab, breakdown_tab, glossary_tab = st.tabs(
        ("Conversation", "Line breakdown", "Glossary")
    )

    with conversation_tab:
        for number, dialogue_line in enumerate(
            (line for line in lesson.passage.splitlines() if line.strip()), start=1
        ):
            _render_japanese_line(
                dialogue_line.strip(),
                points_by_line.get(dialogue_line.strip(), ()),
                show_furigana,
            )
            if show_english and number <= len(line_explanations):
                st.caption(line_explanations[number - 1].english_meaning)

    with breakdown_tab:
        if not line_explanations:
            st.caption("This lesson has no line-by-line explanation.")
        for number, line in enumerate(line_explanations, start=1):
            introduced = _line_points(line)
            summary = ", ".join(point.expression for point in introduced) or "review"
            with st.expander(f"Line {number} — {summary}"):
                _render_japanese_line(
                    line.japanese_text, introduced, show_furigana
                )
                st.write(line.english_meaning)
                for label, points in (
                    ("Kanji", line.kanji),
                    ("Vocabulary", line.vocabulary),
                    ("Grammar", line.grammar),
                ):
                    for point in points:
                        badge = (
                            " ⭐ practice target"
                            if point.expression in target_expressions
                            else ""
                        )
                        st.markdown(
                            f"**{label} · {point.expression}** ({point.reading}){badge}"
                        )
                        st.write(f"{point.meaning}. {point.explanation}")

    with glossary_tab:
        glossary = _glossary(line_explanations)
        if not glossary:
            st.caption("This lesson has no glossary entries.")
        for label, point, line_numbers in glossary:
            lines_text = ", ".join(str(number) for number in line_numbers)
            badge = " ⭐" if point.expression in target_expressions else ""
            st.markdown(
                f"**{point.expression}**{badge} ({point.reading}) · {label} · "
                f"line {lines_text}"
            )
            st.write(f"{point.meaning}. {point.explanation}")

    if isinstance(draft, ActiveLessonDraft):
        future = st.session_state.get("quiz_generation_future")
        quiz_error = st.session_state.get("quiz_generation_error")
        if isinstance(quiz_error, str):
            st.error(quiz_error)
            if generation_service is not None and st.button(
                "Retry quiz preparation", key="retry_quiz_generation"
            ):
                st.session_state.pop("quiz_generation_error", None)
                st.session_state.quiz_generation_future = _start_quiz_generation(
                    generation_service,
                    draft,
                    tuple(service.get_progress(user_id)),
                )
                st.rerun()
        elif isinstance(future, Future):
            if future.done():
                st.caption("Your personalized quiz is ready.")
            else:
                st.caption("Your personalized quiz is being prepared while you study.")
            if st.button("Quiz", type="primary", key="go_to_quiz"):
                with st.spinner("Preparing your personalized quiz..."):
                    try:
                        generated_quiz = future.result()
                    except Exception:
                        st.session_state.pop("quiz_generation_future", None)
                        st.session_state.quiz_generation_error = (
                            "We could not prepare a valid quiz. Your lesson is still available."
                        )
                    else:
                        st.session_state.active_lesson = (
                            service.activate_generated_quiz(draft, generated_quiz)
                        )
                        st.session_state.pop("active_lesson_draft", None)
                        st.session_state.pop("quiz_generation_future", None)
                    st.rerun()
        else:
            st.error("Quiz preparation was interrupted. Your lesson is still available.")
        if st.button("Leave lesson", key="leave_generated_lesson_draft"):
            _clear_active_lesson()
            st.rerun()
        return

    st.subheader("Practice")
    if active.quiz_provider_name is not None:
        st.caption(f"Quiz generated with {active.quiz_provider_name}")
    answer_results = st.session_state.setdefault("lesson_answer_results", {})
    items_by_id = {item.canonical_id: item for item in lesson.items}
    for number, question in enumerate(lesson.questions, start=1):
        st.markdown(f"**{number}. {question.prompt}**")
        st.caption(question.form.value.replace("_", " ").title())
        if question.form is QuestionForm.CONTEXTUAL_CLOZE:
            source_item = items_by_id.get(question.item_id)
            if source_item is not None:
                st.caption(f"From the lesson: {source_item.example}")
        answer_key = f"lesson_answer_{active.lesson_session_id}_{question.question_id}"
        answered = question.question_id in answer_results
        selected_answer = st.radio(
            f"Answer for question {number}",
            display_options(question),
            index=None,
            key=answer_key,
            label_visibility="collapsed",
            disabled=answered,
        )
        confidence = _confidence_input(
            f"lesson_confidence_{active.lesson_session_id}_{question.question_id}",
            answered,
        )
        if answered:
            if answer_results[question.question_id]:
                st.success("Correct.")
            else:
                correct_answer = question.options[question.correct_option_index]
                st.error(f"Not quite. The correct answer is {correct_answer}.")
            st.write(question.explanation)
        elif st.button(
            "Submit answer", key=f"submit_{active.lesson_session_id}_{question.question_id}"
        ):
            if selected_answer is None:
                st.warning("Choose an answer before submitting.")
            else:
                result = service.submit_answer(
                    user_id,
                    active.lesson_session_id,
                    question.question_id,
                    question.options.index(selected_answer),
                    active_lesson=active,
                    confidence=confidence,
                )
                answer_results[question.question_id] = result.is_correct
                st.rerun()

    if len(answer_results) == len(lesson.questions):
        required_retries = [
            retry
            for question, retry in zip(
                lesson.questions, active.retry_questions, strict=True
            )
            if answer_results.get(question.question_id) is False
        ]
        retry_results = st.session_state.setdefault("lesson_retry_results", {})
        if required_retries:
            st.subheader("Corrective practice")
            st.caption(
                "These alternate question forms revisit concepts missed earlier. "
                "Recovery is stored separately from the original answer."
            )
        questions_by_item = {
            question.item_id: question for question in lesson.questions
        }
        for number, retry in enumerate(required_retries, start=1):
            missed = questions_by_item.get(retry.item_id)
            if missed is not None:
                st.info(f"Before you retry: {missed.explanation}")
            st.markdown(f"**Retry {number}. {retry.prompt}**")
            st.caption(retry.form.value.replace("_", " ").title())
            retry_key = f"lesson_retry_{active.lesson_session_id}_{retry.question_id}"
            retried = retry.question_id in retry_results
            selected_retry = st.radio(
                f"Answer for retry {number}",
                display_options(retry),
                index=None,
                key=retry_key,
                label_visibility="collapsed",
                disabled=retried,
            )
            retry_confidence = _confidence_input(
                f"retry_confidence_{active.lesson_session_id}_{retry.question_id}",
                retried,
            )
            if retried:
                if retry_results[retry.question_id]:
                    st.success("Recovered. This counts as Hard, not a first-try success.")
                else:
                    correct_answer = retry.options[retry.correct_option_index]
                    st.error(f"Not quite. The correct answer is {correct_answer}.")
                st.write(retry.explanation)
            elif st.button(
                "Submit retry",
                key=f"submit_retry_{active.lesson_session_id}_{retry.question_id}",
            ):
                if selected_retry is None:
                    st.warning("Choose an answer before submitting.")
                else:
                    result = service.submit_retry_answer(
                        user_id,
                        active.lesson_session_id,
                        retry.question_id,
                        retry.options.index(selected_retry),
                        active_lesson=active,
                        confidence=retry_confidence,
                    )
                    retry_results[retry.question_id] = result.is_correct
                    st.rerun()

    required_retry_count = sum(
        answer_results.get(question.question_id) is False
        for question in lesson.questions
    )
    completed_retry_count = len(st.session_state.get("lesson_retry_results", {}))
    if (
        len(answer_results) == len(lesson.questions)
        and completed_retry_count == required_retry_count
    ):
        st.subheader("Recap")
        st.write(lesson.recap)
        if st.button("Complete lesson", type="primary", key="complete_fixture_lesson"):
            try:
                service.complete_lesson(user_id, active)
            except LessonStateError as error:
                st.error(str(error))
            else:
                _clear_active_lesson()
                st.session_state.last_lesson_completion = True
                st.rerun()

    if st.button("Leave lesson", key="leave_fixture_lesson"):
        _clear_active_lesson()
        st.rerun()


def render_translate() -> None:
    st.title("Translate")
    st.info("Workplace translation will be added in a later increment.")


def render_progress(
    service: LessonService | None = None, user_id: int | None = None
) -> None:
    st.title("Progress")
    if service is None or user_id is None:
        st.info("Sign in to view progress.")
        return
    progress = service.get_progress(user_id)
    if not progress:
        st.info("Start the fixture lesson to create exposure and answered evidence.")
        return

    fixture_items = {item.canonical_id: item for item in FIXTURE_LESSON.items}
    rows = []
    for record in progress:
        item = fixture_items.get(record.item_id)
        rows.append(
            {
                "Item": item.expression if item is not None else record.item_id,
                "Category": record.category.value,
                "Exposures": record.exposure_count,
                "Correct": record.correct_count,
                "Incorrect": record.incorrect_count,
                "Mastery": f"{record.mastery_score:.2f}",
                "Outcome": (
                    record.last_outcome.value.title()
                    if record.last_outcome is not None
                    else "No answers"
                ),
                "Interval": f"{record.sm2_interval_days} days",
                "Ease": f"{record.sm2_ease:.2f}",
                "Successful reviews": record.consecutive_successful_reviews,
                "Next review": (
                    record.next_review_at.isoformat(sep=" ", timespec="minutes")
                    if record.next_review_at is not None
                    else "Not scheduled"
                ),
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")
    completions = service.get_completions(user_id)
    if completions:
        latest = completions[0]
        st.caption(
            f"Latest completed topic: {latest.topic_id} · {latest.difficulty} · "
            f"{latest.completed_at.isoformat(sep=' ', timespec='minutes')}"
        )
    else:
        st.caption("No completed lesson yet. Submitted answers remain valid evidence.")


def _set_suggested_tasks(role_key: str, tasks_key: str) -> None:
    selected_role = st.session_state.get(role_key, "")
    st.session_state[tasks_key] = list(ROLE_TASK_SUGGESTIONS.get(selected_role, ()))


def render_profile_editor(
    service: ProfileService,
    user_id: int,
    profile: ProfileRecord | None,
) -> None:
    onboarding = profile is None
    prefix = f"{'onboarding' if onboarding else 'profile'}_{user_id}"
    role_key = f"{prefix}_role"
    tasks_key = f"{prefix}_tasks"

    if onboarding:
        st.title("Set up your learner profile")
        st.write("Tell us about your work so lessons can match your day-to-day needs.")
    else:
        st.title("Profile")
        st.caption("Update the details used to personalize future lessons.")

    role_options = list(ROLE_TASK_SUGGESTIONS)
    if profile is not None and profile.role not in role_options:
        role_options.insert(0, profile.role)
    selected_role = st.selectbox(
        "Role or title",
        role_options,
        index=role_options.index(profile.role) if profile is not None else 0,
        accept_new_options=True,
        key=role_key,
        help="Search common roles or enter your own.",
        on_change=(
            _set_suggested_tasks
            if onboarding
            else None
        ),
        args=(role_key, tasks_key) if onboarding else None,
    )

    suggested_tasks = list(ROLE_TASK_SUGGESTIONS.get(selected_role, ()))
    selected_tasks = list(profile.tasks) if profile is not None else suggested_tasks
    task_options = list(dict.fromkeys([*selected_tasks, *suggested_tasks]))
    tasks = st.multiselect(
        "Typical tasks",
        task_options,
        default=None if tasks_key in st.session_state else selected_tasks,
        accept_new_options=True,
        key=tasks_key,
        help="Remove suggestions that do not fit, or enter edited and additional tasks.",
    )
    tools_domain = st.text_area(
        "Technologies, tools, or business domain (optional)",
        value=profile.tools_domain or "" if profile is not None else "",
        max_chars=2000,
        key=f"{prefix}_tools_domain",
    )
    level_values = [level.value for level in JapaneseLevel]
    declared_level = st.selectbox(
        "Self-reported Japanese level",
        level_values,
        index=(
            level_values.index(profile.declared_level.value)
            if profile is not None
            else 0
        ),
        key=f"{prefix}_declared_level",
    )
    romaji_preference = st.toggle(
        "Show romaji support",
        value=profile.romaji_preference if profile is not None else False,
        key=f"{prefix}_romaji",
        help="Optional reading support, especially for complete beginners.",
    )

    if profile is None or profile.estimated_working_level is None:
        st.caption("Estimated working level: Not set")
    else:
        st.caption(f"Estimated working level: {profile.estimated_working_level.value}")
    st.button(
        "Take optional placement",
        disabled=True,
        help="Optional placement will be available in a later increment.",
        key=f"{prefix}_placement",
    )

    submit_label = "Save profile" if onboarding else "Save changes"
    if st.button(submit_label, type="primary", key=f"{prefix}_submit"):
        try:
            if onboarding:
                service.create_profile(
                    user_id,
                    role=selected_role,
                    tasks=tasks,
                    tools_domain=tools_domain,
                    declared_level=declared_level,
                    romaji_preference=romaji_preference,
                )
            else:
                service.update_profile(
                    user_id,
                    role=selected_role,
                    tasks=tasks,
                    tools_domain=tools_domain,
                    declared_level=declared_level,
                    romaji_preference=romaji_preference,
                )
        except ProfileValidationError as error:
            st.error(str(error))
        else:
            if onboarding:
                st.rerun()
            st.success("Profile saved.")


def render_profile(
    service: ProfileService | None = None,
    user_id: int | None = None,
    profile: ProfileRecord | None = None,
) -> None:
    if service is None or user_id is None:
        st.title("Profile")
        st.info("Sign in to view your learner profile.")
        return
    render_profile_editor(service, user_id, profile)


PAGE_RENDERERS: dict[str, PageRenderer] = {
    "Home": render_home,
    "Learn": render_learn,
    "Translate": render_translate,
    "Progress": render_progress,
    "Profile": render_profile,
}


def render_health_panel(settings: Settings, engine: Engine) -> None:
    """Show operational readiness without revealing configuration values."""

    health = check_database(engine)

    with st.sidebar.expander("Startup health", expanded=True):
        if health.ready:
            st.success("Database: ready")
            st.caption("SQLite foreign keys: enabled")
        else:
            st.error(f"Database: {health.message.lower()}")

        if settings.model_configured:
            st.success("Model features: configured")
        else:
            st.warning("Model features unavailable: configuration is missing")
        st.caption("Secret values are never displayed.")


def render_authentication(service: AuthenticationService) -> bool:
    st.title("Demo authentication")
    st.caption("Local username and password access for this laptop demo.")
    authenticated = False

    sign_in_tab, register_tab = st.tabs(("Sign in", "Register"))
    with sign_in_tab:
        with st.form("sign_in_form"):
            username = st.text_input("Username", key="sign_in_username")
            password = st.text_input("Password", type="password", key="sign_in_password")
            sign_in = st.form_submit_button("Sign in", type="primary")
        if sign_in:
            try:
                user = service.authenticate(username, password)
            except AuthenticationError as error:
                st.error(str(error))
            else:
                st.session_state.authenticated_user_id = user.id
                st.session_state.authenticated_username = user.username
                authenticated = True

    with register_tab:
        with st.form("registration_form"):
            username = st.text_input("Username", key="registration_username")
            password = st.text_input(
                "Password",
                type="password",
                key="registration_password",
                help="Use 12-128 characters.",
            )
            register = st.form_submit_button("Create account", type="primary")
        if register:
            try:
                user = service.register(username, password)
            except RegistrationError as error:
                st.error(str(error))
            else:
                st.session_state.authenticated_user_id = user.id
                st.session_state.authenticated_username = user.username
                authenticated = True

    return authenticated


def clear_authenticated_session() -> None:
    _clear_active_lesson()
    _clear_active_review()
    st.session_state.pop("last_lesson_completion", None)
    st.session_state.pop("last_review_summary", None)
    st.session_state.pop("authenticated_user_id", None)
    st.session_state.pop("authenticated_username", None)


def main() -> None:
    settings = get_settings()
    st.set_page_config(page_title=settings.app_name, page_icon="🎌", layout="wide")
    st.markdown(JAPANESE_STYLE, unsafe_allow_html=True)
    project_root = Path(__file__).resolve().parents[2]
    engine = create_database_engine(settings, project_root)
    st.sidebar.title(settings.app_name)
    render_health_panel(settings, engine)

    service = AuthenticationService(engine)
    if "authenticated_user_id" not in st.session_state:
        authenticated = render_authentication(service)
        engine.dispose()
        if authenticated:
            st.rerun()
        return

    st.sidebar.caption(
        f"Signed in as {st.session_state.get('authenticated_username', 'local user')}"
    )
    if st.sidebar.button("Sign out"):
        clear_authenticated_session()
        engine.dispose()
        st.rerun()

    user_id = int(st.session_state.authenticated_user_id)
    profile_service = ProfileService(engine)
    lesson_service = LessonService(engine)
    generation_service = None
    if settings.model_configured:
        api_key = settings.model_api_key
        if (
            settings.model_base_url is not None
            and api_key is not None
            and settings.primary_model is not None
            and settings.fallback_model is not None
        ):
            generation_service = _generation_service(
                settings.model_base_url,
                api_key.get_secret_value(),
                settings.primary_model,
                settings.fallback_model,
                settings.model_timeout_seconds,
                settings.primary_model_timeout_seconds,
                settings.hedge_after_seconds,
                settings.parallel_explanations,
                settings.explanation_workers,
                # Route the strict-JSON quiz phase to the structured (fallback) model
                # first, then the primary. Overridable via JLT_QUIZ_* settings.
                settings.quiz_primary_model or settings.fallback_model,
                settings.quiz_fallback_model or settings.primary_model,
            )
    profile = profile_service.get_profile(user_id)
    if profile is None:
        render_profile_editor(profile_service, user_id, None)
        engine.dispose()
        return

    selected_page = st.sidebar.radio(
        "Navigation", PAGE_RENDERERS.keys(), key="navigation"
    )
    if selected_page == "Home":
        render_home(profile, lesson_service, user_id)
    elif selected_page == "Learn":
        render_learn(lesson_service, user_id, profile, generation_service)
    elif selected_page == "Progress":
        render_progress(lesson_service, user_id)
    elif selected_page == "Profile":
        render_profile(profile_service, user_id, profile)
    else:
        PAGE_RENDERERS[selected_page]()
    engine.dispose()


if __name__ == "__main__":
    main()
