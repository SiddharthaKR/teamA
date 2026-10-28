"""User-scoped adapter for the versioned situation route on Home."""

from functools import lru_cache
from dataclasses import replace
from importlib.resources import files
import json

from .core.learning_path import SituationStep, TodayPlan, build_today_plan
from .lesson import LessonService
from .profile import ProfileService
from .schemas.lessons import GeneratedLessonDraft


@lru_cache(maxsize=1)
def load_situation_steps() -> tuple[SituationStep, ...]:
    path = files("japanese_workplace_tutor.resources").joinpath(
        "learning_path_v1.json"
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
    def __init__(self, profiles: ProfileService, lessons: LessonService) -> None:
        self._profiles = profiles
        self._lessons = lessons

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
