"""Measure a passage against the learner: the PRD's 80/20 rule as numbers."""

from collections.abc import Callable
from dataclasses import dataclass

from .language import LEVEL_RANK, LanguageToolkit
from .learner import JapaneseLevel

LEARNER_RANK = {
    JapaneseLevel.COMPLETE_BEGINNER: 1,
    JapaneseLevel.N5: 1,
    JapaneseLevel.N4: 2,
    JapaneseLevel.UNSURE: 2,
    JapaneseLevel.N3: 3,
    JapaneseLevel.N2: 4,
    JapaneseLevel.N1: 5,
}
# Reject only a gross mismatch for now; the team accuracy review calibrates this.
MAX_STRETCH_SHARE = 0.5
MIN_RATED_WORDS = 8


@dataclass(frozen=True)
class DifficultyReport:
    learner_level: str
    familiar: int  # at or below the learner's level, or already mastered
    stretch: int  # above the learner's level
    unrated: int  # not in the reference data (names, rare words)
    stretch_words: tuple[str, ...]

    @property
    def rated(self) -> int:
        return self.familiar + self.stretch

    @property
    def stretch_share(self) -> float:
        return self.stretch / self.rated if self.rated else 0.0

    @property
    def too_hard(self) -> bool:
        return self.rated >= MIN_RATED_WORDS and self.stretch_share > MAX_STRETCH_SHARE


def measure(
    passage: str,
    level: JapaneseLevel,
    toolkit: LanguageToolkit,
    is_mastered: Callable[[str], bool] = lambda lemma: False,
) -> DifficultyReport:
    learner_rank = LEARNER_RANK[level]
    familiar = stretch = unrated = 0
    stretch_words: list[str] = []
    seen: set[str] = set()
    for line in passage.splitlines():
        spoken = line.split(":", 1)[1] if ":" in line else line
        for token in toolkit.tokenize(spoken):
            if not token.is_content or token.lemma in seen:
                continue
            seen.add(token.lemma)
            entry = toolkit.lookup(token.lemma)
            if is_mastered(token.lemma):
                familiar += 1
            elif entry is None or entry.level is None:
                unrated += 1
            elif LEVEL_RANK[entry.level] <= learner_rank:
                familiar += 1
            else:
                stretch += 1
                stretch_words.append(token.lemma)
    return DifficultyReport(level.value, familiar, stretch, unrated, tuple(stretch_words))
