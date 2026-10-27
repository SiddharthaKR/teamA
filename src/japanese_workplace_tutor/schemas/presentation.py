"""Model-facing contracts for the deck localizer and delivery practice."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .roleplay import Comprehensibility


class SlideLocalization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    japanese_title: str = Field(min_length=1, max_length=200, description="Natural Japanese slide title.")
    japanese_body: str = Field(
        min_length=1,
        max_length=2000,
        description="Natural Japanese slide body, concise slide style, not a literal translation.",
    )
    speaker_notes: str = Field(
        min_length=1,
        max_length=1500,
        description="English delivery notes: cushioning phrases, humility, where to hedge, what to say aloud.",
    )
    nuance_notes: str = Field(
        min_length=1,
        max_length=1500,
        description="English: what was changed versus a literal translation and why (register, katakana-English avoided).",
    )


class FlowSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    position: int = Field(ge=1, description="Recommended 1-based position in the running order.")
    slide_title: str = Field(min_length=1, max_length=200, description="Which slide, echoing its English title.")
    rationale: str = Field(min_length=1, max_length=300, description="English: why it belongs here.")


class DeckFlowReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment: str = Field(
        min_length=1,
        max_length=1500,
        description="English: how well the current order fits Japanese business-deck norms, and the key change.",
    )
    recommended_order: tuple[FlowSuggestion, ...] = Field(min_length=1, max_length=20)


@dataclass(frozen=True)
class LocalizedDeck:
    slides: tuple[SlideLocalization, ...]
    flow_review: DeckFlowReview
    provider_name: str


# --------------------------------------------------------------------------- #
# Practice presenting: coach the user to DELIVER a Japanese deck slide by slide,
# then let them rehearse each slide and get feedback. The model proposes the
# coaching and the per-slide judgement; the app decides pass/fail deterministically
# (evaluate_delivery), the same "LLM proposes, app disposes" rule used elsewhere.
# --------------------------------------------------------------------------- #
class SlideDeliveryCoaching(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key_message: str = Field(
        min_length=1, max_length=300, description="English: the one thing this slide must land."
    )
    spoken_script: str = Field(
        min_length=1,
        max_length=1200,
        description="Japanese: a natural spoken narration to say aloud for this slide (fuller than the slide text).",
    )
    transition_in: str = Field(
        min_length=1,
        max_length=200,
        description="Japanese: a phrase to move into this slide from the previous one.",
    )
    delivery_tips: str = Field(
        min_length=1,
        max_length=800,
        description="English: pace, emphasis, keigo, and where to pause when presenting this slide.",
    )
    rehearsal_options: tuple[str, ...] = Field(
        min_length=3,
        max_length=4,
        description="Japanese candidate one-line deliveries for this slide; one strong, others plausible mistakes (too casual, or off the key message).",
    )

    @model_validator(mode="after")
    def _distinct_options(self) -> "SlideDeliveryCoaching":
        if len(set(self.rehearsal_options)) != len(self.rehearsal_options):
            raise ValueError("rehearsal_options must be distinct.")
        return self


class DeliveryVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    covers_key_message: bool
    coverage_evidence: str = Field(min_length=1, max_length=300)
    comprehensible: Comprehensibility
    comprehensible_evidence: str = Field(min_length=1, max_length=300)
    register_appropriate: bool
    register_evidence: str = Field(min_length=1, max_length=300)
    improvement_tip: str = Field(
        min_length=1, max_length=300, description="English: one concrete way to deliver it better."
    )


@dataclass(frozen=True)
class CoachedDeck:
    slides: tuple[SlideDeliveryCoaching, ...]
    provider_name: str


@dataclass(frozen=True)
class DeliveryJudgement:
    verdict: DeliveryVerdict
    provider_name: str


@dataclass(frozen=True)
class DeliveryResult:
    passed: bool
    failed_criteria: tuple[str, ...]
