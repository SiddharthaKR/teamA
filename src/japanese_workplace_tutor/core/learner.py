"""The learner as the domain sees them: level and role context, no persistence."""

from dataclasses import dataclass
from enum import StrEnum


class JapaneseLevel(StrEnum):
    COMPLETE_BEGINNER = "Complete beginner"
    N5 = "JLPT N5"
    N4 = "JLPT N4"
    N3 = "JLPT N3"
    N2 = "JLPT N2"
    N1 = "JLPT N1"
    UNSURE = "Unsure"


class LevelSource(StrEnum):
    SELF_REPORTED = "self-reported"
    PLACEMENT_ESTIMATED = "placement-estimated"
    PERFORMANCE_ESTIMATED = "performance-estimated"


@dataclass(frozen=True)
class ProfileRecord:
    user_id: int
    role: str
    tasks: tuple[str, ...]
    tools_domain: str | None
    declared_level: JapaneseLevel
    estimated_working_level: JapaneseLevel | None
    level_source: LevelSource
    level_confidence: float
    romaji_preference: bool
    milestone_id: str = "get-by"
