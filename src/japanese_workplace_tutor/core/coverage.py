"""Coverage and milestones: how much of a target set a learner has mastered.

Pure functions over reference sets and mastered item ids. A milestone is the
finish line a learner works toward (decision 13): its word and grammar sets
must reach a coverage target, and its task checks (Phase 4) must pass.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from .language import WordSet


@dataclass(frozen=True)
class Coverage:
    set_id: str
    label: str
    kind: str
    mastered: int
    total: int

    @property
    def share(self) -> float:
        return self.mastered / self.total if self.total else 0.0


@dataclass(frozen=True)
class Milestone:
    id: str
    name: str
    summary: str
    cefr_hint: str
    word_sets: tuple[str, ...]
    coverage_target: float
    tasks: Mapping[str, tuple[str, ...]]  # "read" / "write" / "speak" -> can-do statements


@dataclass(frozen=True)
class MilestoneProgress:
    milestone: Milestone
    mastered: int
    total: int
    parts: tuple[Coverage, ...]

    @property
    def share(self) -> float:
        return self.mastered / self.total if self.total else 0.0

    @property
    def words_ready(self) -> bool:
        """The word and grammar part of the checklist; task checks come later."""

        return self.total > 0 and self.share >= self.milestone.coverage_target


def coverage(word_set: WordSet, is_mastered: Callable[[str], bool]) -> Coverage:
    mastered = sum(1 for member in word_set.members if is_mastered(member))
    return Coverage(word_set.id, word_set.label, word_set.kind, mastered, len(word_set.members))


def coverages(
    word_sets: Iterable[WordSet],
    is_word_mastered: Callable[[str], bool],
    is_grammar_mastered: Callable[[str], bool],
) -> tuple[Coverage, ...]:
    return tuple(
        coverage(word_set, is_grammar_mastered if word_set.kind == "grammar" else is_word_mastered)
        for word_set in word_sets
    )


def milestones_progress(
    milestones: Sequence[Milestone],
    word_sets: Iterable[WordSet],
    all_coverage: Sequence[Coverage],
    is_word_mastered: Callable[[str], bool],
    is_grammar_mastered: Callable[[str], bool],
) -> tuple[MilestoneProgress, ...]:
    """Progress per milestone over the union of its sets, so a word that is in two
    of its sets (会議: JLPT N4 and Business: meetings) counts once."""

    sets_by_id = {word_set.id: word_set for word_set in word_sets}
    coverage_by_id = {item.set_id: item for item in all_coverage}
    results = []
    for milestone in milestones:
        chosen = [sets_by_id[set_id] for set_id in milestone.word_sets if set_id in sets_by_id]
        words = frozenset().union(*(s.members for s in chosen if s.kind == "words"))
        grammar = frozenset().union(*(s.members for s in chosen if s.kind == "grammar"))
        mastered = sum(1 for lemma in words if is_word_mastered(lemma)) + sum(
            1 for point in grammar if is_grammar_mastered(point)
        )
        parts = tuple(coverage_by_id[s.id] for s in chosen if s.id in coverage_by_id)
        results.append(MilestoneProgress(milestone, mastered, len(words) + len(grammar), parts))
    return tuple(results)
