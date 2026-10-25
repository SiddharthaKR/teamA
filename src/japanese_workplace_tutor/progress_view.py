"""The learner's progress view (decision 13): named items with a status, coverage of
each reference set, and progress toward the milestone finish lines.

Everything here is computed by code from stored progress and the reference lists;
nothing comes from the model.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import resources
import json

from .core.coverage import Coverage, Milestone, MilestoneProgress, coverages, milestones_progress
from .core.history import (
    AnswerPoint,
    WeekPoint,
    WeekSummary,
    answer_points,
    mastered_at,
    this_week,
    weekly_history,
)
from .core.items import ItemCategory
from .core.language import LanguageToolkit
from .core.progress import Answer, ItemStatus, ProgressRecord, item_status
from .features.lessons import canonical_item_id

STATUS_ORDER = (ItemStatus.SLIPPING, ItemStatus.LEARNING, ItemStatus.NEW, ItemStatus.MASTERED)
UNNAMED = "(name not saved)"


@dataclass(frozen=True)
class ItemRow:
    item_id: str
    name: str
    category: str
    status: ItemStatus
    mastery: float
    next_review_at: datetime | None


@dataclass(frozen=True)
class ProgressView:
    items: tuple[ItemRow, ...]
    status_counts: dict[ItemStatus, int]
    coverage: tuple[Coverage, ...]
    milestones: tuple[MilestoneProgress, ...]


def load_milestones() -> tuple[Milestone, ...]:
    data = json.loads(
        resources.files("japanese_workplace_tutor.resources")
        .joinpath("milestones_v1.json")
        .read_text(encoding="utf-8")
    )
    return tuple(
        Milestone(
            id=raw["id"],
            name=raw["name"],
            summary=raw["summary"],
            cefr_hint=raw["cefr_hint"],
            word_sets=tuple(raw["word_sets"]),
            coverage_target=float(raw["coverage_target"]),
            tasks={kind: tuple(items) for kind, items in raw["tasks"].items()},
        )
        for raw in data["milestones"]
    )


def build_progress_view(
    records: Sequence[ProgressRecord],
    now: datetime,
    toolkit: LanguageToolkit | None = None,
    milestones: Sequence[Milestone] = (),
) -> ProgressView:
    rows = tuple(
        sorted(
            (
                ItemRow(
                    item_id=record.item_id,
                    name=record.expression or UNNAMED,
                    category=record.category.value,
                    status=item_status(record, now),
                    mastery=record.mastery_score,
                    next_review_at=record.next_review_at,
                )
                for record in records
            ),
            key=lambda row: (STATUS_ORDER.index(row.status), row.name),
        )
    )
    counts = Counter(row.status for row in rows)
    status_counts = {status: counts.get(status, 0) for status in STATUS_ORDER}
    if toolkit is None:
        return ProgressView(rows, status_counts, (), ())

    mastered = {row.item_id for row in rows if row.status is ItemStatus.MASTERED}
    word_mastered, grammar_mastered = _mastery_tests(mastered, toolkit)
    word_sets = toolkit.word_sets()
    all_coverage = coverages(word_sets, word_mastered, grammar_mastered)
    return ProgressView(
        rows,
        status_counts,
        all_coverage,
        milestones_progress(milestones, word_sets, all_coverage, word_mastered, grammar_mastered),
    )


def _mastery_tests(mastered: set[str] | frozenset[str], toolkit: LanguageToolkit):
    def word_mastered(lemma: str) -> bool:
        return bool(mastered) and any(
            canonical_item_id(category, lemma, toolkit) in mastered
            for category in (ItemCategory.KANJI, ItemCategory.VOCABULARY)
        )

    def grammar_mastered(point_id: str) -> bool:
        return f"grammar:{point_id}" in mastered

    return word_mastered, grammar_mastered


CHANGE_WINDOW = timedelta(weeks=4)


@dataclass(frozen=True)
class ProgressHistory:
    """Progress over time (decision 15): weeks, this week, and 4-week milestone change."""

    weeks: tuple[WeekPoint, ...]
    this_week: WeekSummary
    milestone_change: dict[str, float]  # milestone id -> change in share over 4 weeks


def build_progress_history(
    answers_by_item: dict[str, Sequence[Answer]],
    now: datetime,
    toolkit: LanguageToolkit | None = None,
    milestones: Sequence[Milestone] = (),
) -> ProgressHistory:
    points: dict[str, tuple[AnswerPoint, ...]] = {
        item_id: answer_points(item_id, answers) for item_id, answers in answers_by_item.items()
    }
    change: dict[str, float] = {}
    if toolkit is not None and milestones:
        word_sets = toolkit.word_sets()
        shares = []
        for moment in (now - CHANGE_WINDOW, now + timedelta(microseconds=1)):
            word_mastered, grammar_mastered = _mastery_tests(mastered_at(points, moment), toolkit)
            parts = coverages(word_sets, word_mastered, grammar_mastered)
            shares.append(
                {
                    item.milestone.id: item.share
                    for item in milestones_progress(milestones, word_sets, parts, word_mastered, grammar_mastered)
                }
            )
        change = {milestone_id: shares[1][milestone_id] - shares[0][milestone_id] for milestone_id in shares[1]}
    return ProgressHistory(weekly_history(points, now), this_week(points, now), change)
