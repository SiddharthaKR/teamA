"""Pure selection of a learner's next milestone situation and due-review lane."""

from dataclasses import dataclass
from collections.abc import Sequence


@dataclass(frozen=True)
class SituationStep:
    id: str
    milestone_id: str
    title: str
    scenario: str
    track: str = "situation"
    words: tuple[str, ...] = ()
    grammar: str | None = None
    chunks: tuple[str, ...] = ()
    answer: str | None = None

    @property
    def topic_id(self) -> str:
        return f"path:{self.id}"


def route_scenario_matches(
    step: SituationStep | None, suggested: str | None, submitted: str,
) -> bool:
    return bool(step and step.track == "words" and suggested == submitted)


def grade_order(
    chunks: Sequence[str], indices: Sequence[int], answer: str,
) -> bool | None:
    """Check a curated phrase exactly; ambiguous chunk sets stay practice only."""
    if (len(chunks) < 2 or len(set(chunks)) != len(chunks)
            or sorted(indices) != list(range(len(chunks)))
            or not answer or "".join(chunks) != answer):
        return None
    return "".join(chunks[index] for index in indices) == answer


@dataclass(frozen=True)
class TodayPlan:
    review_count: int
    next_step: SituationStep | None
    completed_steps: int
    total_steps: int
    reason: str
    local_alternative: SituationStep | None = None


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
    local_alternative = next((step for step in route
                              if step.track in {"grammar", "sentence-order"}
                              and step.topic_id not in completed_ids), None)
    if next_step is None:
        reason = "You have completed these route steps. Choose free practice."
    elif completed_count == 0:
        reason = f"Your first {next_step.track.replace('-', ' ')} step for this milestone."
    else:
        reason = f"Next {next_step.track.replace('-', ' ')} step in your milestone path."
    return TodayPlan(min(max(due_count, 0), 5), next_step,
                     completed_count, len(route), reason, local_alternative)
