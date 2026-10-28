"""User-scoped adapter for the versioned situation route on Home."""

from functools import lru_cache
from dataclasses import replace
from importlib.resources import files
import json

from .core.learning_path import SituationStep, TodayPlan, build_today_plan, grade_order
from .core.language import LanguageToolkit
from .lesson import LessonService
from .profile import ProfileService
from .schemas.lessons import GeneratedLessonDraft


@lru_cache(maxsize=1)
def load_situation_steps() -> tuple[SituationStep, ...]:
    path = files("japanese_workplace_tutor.resources").joinpath(
        "learning_path_v2.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(SituationStep(**row) for row in data["steps"])


def tag_today_draft(
    draft: GeneratedLessonDraft, topic_id: str | None,
    suggested_scenario: str | None, submitted_scenario: str,
    *, mock_mode: bool,
) -> GeneratedLessonDraft:
    """Record a completed route only for its exact requested real-model lesson."""
    if (mock_mode or not topic_id or submitted_scenario != suggested_scenario
            or topic_id not in {step.topic_id for step in load_situation_steps()}):
        return draft
    return replace(draft, content=draft.content.model_copy(update={"topic_id": topic_id}))


class TodayService:
    def __init__(self, profiles: ProfileService, lessons: LessonService,
                 toolkit: LanguageToolkit | None = None) -> None:
        self._profiles = profiles
        self._lessons = lessons
        self._toolkit = toolkit

    def grammar_question(self, step: SituationStep) -> tuple[str, tuple[str, ...]] | None:
        if self._toolkit is None or step.track != "grammar" or not step.grammar:
            return None
        point = self._toolkit.grammar_point(step.grammar)
        if point is None or not point.meanings:
            return None
        options = tuple(dict.fromkeys(
            row.grammar for row in load_situation_steps()
            if row.track == "grammar" and row.grammar
        )) + ("〜ません",)
        return point.meanings[0], options

    def submit_practice(
        self, user_id: int, topic_id: str, answer: str | tuple[int, ...],
    ) -> bool:
        """Check a local grammar or ordering answer before recording coverage."""
        profile = self._profiles.get_profile(user_id)
        step = next((row for row in load_situation_steps()
                     if row.topic_id == topic_id and profile is not None
                     and row.milestone_id == profile.milestone_id), None)
        if step is None or self._toolkit is None:
            return False
        if step.track == "grammar" and isinstance(answer, str):
            correct = bool(step.grammar and self._toolkit.grammar_point(step.grammar)
                           and answer == step.grammar)
        elif step.track == "sentence-order" and isinstance(answer, tuple):
            reference = self._toolkit.lookup(step.answer or "")
            correct = bool(reference and reference.business_group and step.answer
                           and grade_order(step.chunks, answer, step.answer) is True)
        else:
            return False
        if correct:
            self._lessons.record_practice_completion(user_id, topic_id)
        return correct

    def build_today_plan(self, user_id: int) -> TodayPlan | None:
        profile = self._profiles.get_profile(user_id)
        if profile is None:
            return None
        completions = self._lessons.get_completions(user_id)
        return build_today_plan(
            profile.milestone_id, load_situation_steps(),
            tuple(row.topic_id for row in completions),
            due_count=self._lessons.get_due_count(user_id),
        )
