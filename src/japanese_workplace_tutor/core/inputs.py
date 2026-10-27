"""Validated learner inputs and request shaping shared by prompts and features."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .learner import JapaneseLevel, ProfileRecord

MAX_SCENARIO_LENGTH = 4000
DEFAULT_LINE_COUNT = 10
# Shorter dialogues at lower levels cut generation latency as well as reading load.
# Complete beginners get the shortest dialogue and "Unsure" a middle length, so the
# longest lesson is never the default for someone who has not placed themselves.
LINE_COUNT_BY_LEVEL = {
    JapaneseLevel.COMPLETE_BEGINNER: 6,
    JapaneseLevel.N5: 6,
    JapaneseLevel.N4: 8,
    JapaneseLevel.UNSURE: 8,
    JapaneseLevel.N3: 10,
}


class ScenarioMode(StrEnum):
    GENERATE = "Generate a lesson from this scenario"
    EXPLAIN = "Explain this Japanese text"


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(max_length=MAX_SCENARIO_LENGTH)
    mode: ScenarioMode

    @field_validator("scenario")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
            raise ValueError("Scenario contains unsupported control characters.")
        return value

    @model_validator(mode="after")
    def require_text_for_explain_mode(self) -> "ScenarioInput":
        if self.mode is ScenarioMode.EXPLAIN and not self.scenario.strip():
            raise ValueError("Japanese text is required in Explain mode.")
        return self


def detect_scenario_mode(scenario: str) -> ScenarioMode:
    has_japanese = any(
        "\u3040" <= character <= "\u30ff" or "\u3400" <= character <= "\u9fff"
        for character in scenario
    )
    return ScenarioMode.EXPLAIN if has_japanese else ScenarioMode.GENERATE


def expected_line_count(profile: ProfileRecord) -> int:
    level = profile.estimated_working_level or profile.declared_level
    return LINE_COUNT_BY_LEVEL.get(level, DEFAULT_LINE_COUNT)


# --------------------------------------------------------------------------- #
# Presentation localizer: turn an English deck into natural Japanese to paste,
# fixing the four things that get a deck spotted as AI: register/keigo, literal
# phrasing, slide-order flow, and missing delivery nuance. Output only; the
# author's design and slide order stay theirs.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SlideInput:
    title: str
    body: str
