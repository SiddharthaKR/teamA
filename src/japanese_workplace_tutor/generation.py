"""Public entry point for model-backed features (stable import path for the app).

LessonGenerationService wires one LLMGateway into the lesson, roleplay and
presentation features. Logic lives in those modules:

* core/       pure domain types and rules (no IO)
* schemas/    model-facing response contracts
* prompts/    versioned prompt builders
* llm/        the gateway (routing, repair, fallback) and transport adapters
* features/   orchestration and acceptance rules per feature
"""

from collections.abc import Mapping, Sequence

from .core.errors import GenerationError
from .core.inputs import (
    DEFAULT_LINE_COUNT,
    LINE_COUNT_BY_LEVEL,
    MAX_SCENARIO_LENGTH,
    ScenarioInput,
    ScenarioMode,
    SlideInput,
    detect_scenario_mode,
    expected_line_count,
)
from .core.items import LessonContent
from .core.language import LanguageToolkit
from .core.learner import ProfileRecord
from .core.ports import DataClass, ModelTransport
from .core.progress import ProgressRecord
from .features.lessons import LessonGenerator, canonical_item_id
from .features.presentation import PresentationCoach, evaluate_delivery
from .features.roleplay import RoleplayCoach, evaluate_graduation
from .language.sudachi_toolkit import SudachiToolkit
from .llm.gateway import LLMGateway, provider_label
from .llm.openai_transport import OpenAICompatibleTransport, extract_json_text
from .schemas.lessons import (
    GeneratedConversationResponse,
    GeneratedLessonContentPackage,
    GeneratedLessonDraft,
    GeneratedQuiz,
    GeneratedQuizPackage,
)
from .schemas.presentation import (
    CoachedDeck,
    DeckFlowReview,
    DeliveryJudgement,
    DeliveryResult,
    DeliveryVerdict,
    LocalizedDeck,
    SlideDeliveryCoaching,
    SlideLocalization,
)
from .schemas.roleplay import (
    Comprehensibility,
    GeneratedChallenge,
    GraduationResult,
    Recovery,
    RoleplayJudgement,
    RoleplayVerdict,
    SituationChallenge,
)

__all__ = [
    "CoachedDeck", "Comprehensibility", "DEFAULT_LINE_COUNT", "DataClass", "DeckFlowReview",
    "DeliveryJudgement", "DeliveryResult", "DeliveryVerdict", "GeneratedChallenge",
    "GeneratedConversationResponse", "GeneratedLessonContentPackage", "GeneratedLessonDraft",
    "GeneratedQuiz", "GeneratedQuizPackage", "GenerationError", "GraduationResult",
    "LINE_COUNT_BY_LEVEL", "LessonGenerationService", "LocalizedDeck", "MAX_SCENARIO_LENGTH",
    "ModelTransport", "OpenAICompatibleTransport", "Recovery", "RoleplayJudgement",
    "RoleplayVerdict", "ScenarioInput", "ScenarioMode", "SituationChallenge", "SlideDeliveryCoaching",
    "SlideInput", "SlideLocalization", "canonical_item_id", "detect_scenario_mode",
    "evaluate_delivery", "evaluate_graduation", "expected_line_count", "extract_json_text",
    "provider_label",
]


class LessonGenerationService:
    """Composition of the gateway and the three model-backed features."""

    def __init__(
        self,
        transport: ModelTransport,
        primary_model: str,
        fallback_model: str,
        primary_timeout_seconds: float | None = None,
        hedge_after_seconds: float | None = None,
        parallel_explanations: bool = False,
        explanation_workers: int = 4,
        quiz_primary_model: str | None = None,
        quiz_fallback_model: str | None = None,
        toolkit: LanguageToolkit | None = None,
    ) -> None:
        self.gateway = LLMGateway(
            transport,
            primary_model,
            fallback_model,
            primary_timeout_seconds=primary_timeout_seconds,
            hedge_after_seconds=hedge_after_seconds,
            quiz_primary_model=quiz_primary_model,
            quiz_fallback_model=quiz_fallback_model,
        )
        self.toolkit = toolkit or SudachiToolkit.shared()
        self.lessons = LessonGenerator(
            self.gateway, self.toolkit, parallel_explanations, explanation_workers
        )
        self.roleplay = RoleplayCoach(self.gateway)
        self.presentation = PresentationCoach(self.gateway, explanation_workers)

    def generate_lesson_content(
        self,
        scenario: str,
        mode: ScenarioMode,
        profile: ProfileRecord,
        learning_history: Sequence[ProgressRecord] = (),
        recent_topic_ids: Sequence[str] = (),
    ) -> GeneratedLessonDraft:
        return self.lessons.generate_lesson_content(
            scenario, mode, profile, learning_history, recent_topic_ids
        )

    def generate_quiz(
        self, content: LessonContent, learning_history: Sequence[ProgressRecord] = ()
    ) -> GeneratedQuiz:
        return self.lessons.generate_quiz(content, learning_history)

    def generate_situation_challenge(
        self, content: LessonContent, profile: ProfileRecord
    ) -> GeneratedChallenge:
        return self.roleplay.generate_situation_challenge(content, profile)

    def judge_roleplay(
        self, challenge: SituationChallenge, opening_reply: str, curveball_reply: str
    ) -> RoleplayJudgement:
        return self.roleplay.judge_roleplay(challenge, opening_reply, curveball_reply)

    def localize_deck(
        self,
        slides: Sequence[SlideInput],
        context: Mapping[str, str],
        profile: ProfileRecord | None = None,
    ) -> LocalizedDeck:
        return self.presentation.localize_deck(slides, context, profile)

    def coach_deck_delivery(
        self,
        slides: Sequence[SlideInput],
        context: Mapping[str, str],
        profile: ProfileRecord | None = None,
    ) -> CoachedDeck:
        return self.presentation.coach_deck_delivery(slides, context, profile)

    def judge_delivery(
        self,
        coaching: SlideDeliveryCoaching,
        slide: SlideInput,
        learner_delivery: str,
        context: Mapping[str, str],
    ) -> DeliveryJudgement:
        return self.presentation.judge_delivery(coaching, slide, learner_delivery, context)
