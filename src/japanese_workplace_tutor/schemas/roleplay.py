"""Model-facing contracts for situation roleplay."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --------------------------------------------------------------------------- #
# Situation roleplay: the production/recovery stage after the quiz.
# The model proposes the challenge and the per-criterion judgement; the app
# decides pass/fail deterministically (see evaluate_graduation), matching the
# "LLM proposes, app disposes" rule used for scoring elsewhere.
# --------------------------------------------------------------------------- #
class RoleplayToolkitPhrase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    japanese: str = Field(min_length=1, max_length=100)
    reading: str = Field(min_length=1, max_length=100)
    meaning: str = Field(min_length=1, max_length=200, description="English meaning.")
    kind: str = Field(
        min_length=1,
        max_length=20,
        description="'target' for a lesson item, 'recovery' for a repair/clarify phrase.",
    )


class SituationChallenge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=1, max_length=300, description="English: the real-world outcome to achieve.")
    setting: str = Field(min_length=1, max_length=300, description="English: where/when this happens.")
    learner_role: str = Field(min_length=1, max_length=150, description="English.")
    counterpart_role: str = Field(min_length=1, max_length=150, description="English, e.g. 'your manager'.")
    success_criteria: tuple[str, ...] = Field(
        min_length=3, max_length=4, description="English observable pass criteria."
    )
    toolkit: tuple[RoleplayToolkitPhrase, ...] = Field(min_length=2, max_length=8)
    opening_line: str = Field(min_length=1, max_length=300, description="Japanese: the counterpart's first line.")
    opening_options: tuple[str, ...] = Field(
        min_length=3,
        max_length=4,
        description="Japanese candidate learner replies to the opening; one clearly appropriate, others plausible mistakes (too casual, or off-goal).",
    )
    curveball_type: str = Field(min_length=1, max_length=40, description="Short label, e.g. 'follow-up question'.")
    curveball_line: str = Field(min_length=1, max_length=300, description="Japanese: one unexpected line the counterpart says next.")
    curveball_options: tuple[str, ...] = Field(
        min_length=3,
        max_length=4,
        description="Japanese candidate learner replies to the curveball; one appropriate recovery, others plausible mistakes.",
    )

    @model_validator(mode="after")
    def _distinct_options(self) -> "SituationChallenge":
        for label, options in (("opening", self.opening_options), ("curveball", self.curveball_options)):
            if len(set(options)) != len(options):
                raise ValueError(f"{label}_options must be distinct.")
        return self


class Comprehensibility(StrEnum):
    YES = "yes"
    MOSTLY = "mostly"
    NO = "no"


class Recovery(StrEnum):
    YES = "yes"
    PARTLY = "partly"
    NO = "no"


class RoleplayVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_achieved: bool
    goal_evidence: str = Field(min_length=1, max_length=300)
    comprehensible: Comprehensibility
    comprehensible_evidence: str = Field(min_length=1, max_length=300)
    register_appropriate: bool
    register_evidence: str = Field(min_length=1, max_length=300)
    recovered_from_curveball: Recovery
    recovery_evidence: str = Field(min_length=1, max_length=300)


@dataclass(frozen=True)
class GeneratedChallenge:
    challenge: SituationChallenge
    provider_name: str


@dataclass(frozen=True)
class RoleplayJudgement:
    verdict: RoleplayVerdict
    provider_name: str


@dataclass(frozen=True)
class GraduationResult:
    graduated: bool
    failed_criteria: tuple[str, ...]
