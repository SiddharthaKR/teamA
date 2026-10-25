"""Progress over time, replayed from the answer log (decision 15).

Answers are stored once and never changed, so replaying them through the same
policy rebuilds a learner's mastery at any past moment. Nothing extra is stored.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .progress import Answer, ItemState, PastAttempt, ProgressPolicy, SM2MasteryPolicy

# Weeks start on Monday 00:00 Japan time. Japan has no daylight saving time, so a
# fixed offset is exact (and needs no time zone database on Windows).
LOCAL_OFFSET = timedelta(hours=9)
# A "recall" answer comes at least this long after the item's previous answer:
# remembering after a gap, not straight after studying.
RECALL_GAP = timedelta(hours=12)
MASTERY_THRESHOLD = SM2MasteryPolicy.MASTERY_THRESHOLD


@dataclass(frozen=True)
class AnswerPoint:
    item_id: str
    answered_at: datetime
    mastery_after: float
    after_gap: bool
    is_correct: bool


@dataclass(frozen=True)
class WeekPoint:
    week: date  # Monday, Japan time
    mastered: int  # items at mastery 0.80 or more at the end of the week
    recall_correct: int
    recall_total: int

    @property
    def recall_rate(self) -> float | None:
        return self.recall_correct / self.recall_total if self.recall_total else None


@dataclass(frozen=True)
class WeekSummary:
    week: date
    newly_mastered: int  # items that reached mastery for the first time this week
    answers: int
    recall_correct: int
    recall_total: int

    @property
    def recall_rate(self) -> float | None:
        return self.recall_correct / self.recall_total if self.recall_total else None


def answer_points(
    item_id: str, answers: Sequence[Answer], policy: ProgressPolicy | None = None
) -> tuple[AnswerPoint, ...]:
    """Mastery after each answer, in time order, for one item."""

    policy = policy or SM2MasteryPolicy()
    state = ItemState()
    history: list[PastAttempt] = []
    points: list[AnswerPoint] = []
    previous: datetime | None = None
    for answer in sorted(answers, key=lambda candidate: candidate.answered_at):
        outcome = policy.outcome(state, history, answer)
        state = policy.apply(state, history, answer, outcome)
        after_gap = (
            previous is not None
            and not answer.is_retry
            and answer.answered_at - previous >= RECALL_GAP
        )
        points.append(
            AnswerPoint(item_id, answer.answered_at, state.mastery_score, after_gap, answer.is_correct)
        )
        history.append(
            PastAttempt(answer.lesson_session_id, answer.question_form.value, answer.is_correct)
        )
        previous = answer.answered_at
    return tuple(points)


def week_of(moment: datetime) -> date:
    local = (moment + LOCAL_OFFSET).date()
    return local - timedelta(days=local.weekday())


def week_start(week: date) -> datetime:
    """The week's Monday 00:00 Japan time, as naive UTC like the stored times."""

    return datetime.combine(week, time()) - LOCAL_OFFSET


def mastered_at(points_by_item: Mapping[str, Sequence[AnswerPoint]], moment: datetime) -> frozenset[str]:
    """Items whose latest answer before `moment` left them at mastery 0.80 or more."""

    mastered = set()
    for item_id, points in points_by_item.items():
        latest = None
        for point in points:
            if point.answered_at >= moment:
                break
            latest = point
        if latest is not None and latest.mastery_after >= MASTERY_THRESHOLD:
            mastered.add(item_id)
    return frozenset(mastered)


def _all(points_by_item: Mapping[str, Sequence[AnswerPoint]]) -> Iterable[AnswerPoint]:
    for points in points_by_item.values():
        yield from points


def weekly_history(
    points_by_item: Mapping[str, Sequence[AnswerPoint]], now: datetime, max_weeks: int = 26
) -> tuple[WeekPoint, ...]:
    everything = list(_all(points_by_item))
    if not everything:
        return ()
    current = week_of(now)
    first = max(week_of(min(point.answered_at for point in everything)), current - timedelta(weeks=max_weeks - 1))
    weeks = []
    week = first
    while week <= current:
        end = min(week_start(week) + timedelta(weeks=1), now + timedelta(microseconds=1))
        recalls = [point for point in everything if point.after_gap and week_of(point.answered_at) == week]
        weeks.append(
            WeekPoint(
                week,
                len(mastered_at(points_by_item, end)),
                sum(point.is_correct for point in recalls),
                len(recalls),
            )
        )
        week += timedelta(weeks=1)
    return tuple(weeks)


def this_week(points_by_item: Mapping[str, Sequence[AnswerPoint]], now: datetime) -> WeekSummary:
    week = week_of(now)
    newly = 0
    for points in points_by_item.values():
        first = next((point for point in points if point.mastery_after >= MASTERY_THRESHOLD), None)
        if first is not None and week_of(first.answered_at) == week:
            newly += 1
    current = [point for point in _all(points_by_item) if week_of(point.answered_at) == week]
    recalls = [point for point in current if point.after_gap]
    return WeekSummary(week, newly, len(current), sum(point.is_correct for point in recalls), len(recalls))
