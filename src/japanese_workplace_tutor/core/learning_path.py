"""Pure selection of a learner's next milestone situation and due-review lane."""

from dataclasses import dataclass
from collections.abc import Sequence


@dataclass(frozen=True)
class SituationStep:
    id: str
    milestone_id: str
    title: str
    scenario: str

    @property
    def topic_id(self) -> str:
        return f"path:{self.id}"


@dataclass(frozen=True)
class TodayPlan:
    review_count: int
    next_step: SituationStep | None
    completed_steps: int
    total_steps: int
    reason: str


def build_today_plan(
    milestone_id: str,
    steps: Sequence[SituationStep],
    completed_topic_ids: Sequence[str],
    *,
    due_count: int,
) -> TodayPlan:
    """Return one next situation; repeated completions count only once."""
    route = tuple(step for step in steps if step.milestone_id == milestone_id)
    completed_ids = set(completed_topic_ids)
    completed_count = sum(step.topic_id in completed_ids for step in route)
    next_step = next((step for step in route if step.topic_id not in completed_ids), None)
    if next_step is None:
        reason = "You have completed these situation routes. Choose free practice."
    elif completed_count == 0:
        reason = "Your first situation for this milestone."
    else:
        reason = "Next situation in your milestone path."
    return TodayPlan(min(max(due_count, 0), 5), next_step,
                     completed_count, len(route), reason)
