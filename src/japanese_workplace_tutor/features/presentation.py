"""Deck localizer and delivery practice features."""

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from ..core.errors import GenerationError
from ..core.inputs import SlideInput
from ..core.learner import ProfileRecord
from ..core.ports import DataClass
from ..llm.gateway import LLMGateway
from ..prompts import presentation as prompts
from ..schemas.presentation import (
    CoachedDeck,
    DeckFlowReview,
    DeliveryJudgement,
    DeliveryResult,
    DeliveryVerdict,
    LocalizedDeck,
    SlideDeliveryCoaching,
    SlideLocalization,
)
from ..schemas.roleplay import Comprehensibility


def evaluate_delivery(verdict: DeliveryVerdict) -> DeliveryResult:
    """Deterministic per-slide pass: the delivery covers the key message, is at
    least mostly comprehensible, and uses an appropriate register. Comprehensibility
    is judged over grammatical perfection on purpose."""

    checks = {
        "key message": verdict.covers_key_message,
        "comprehensibility": verdict.comprehensible in (Comprehensibility.YES, Comprehensibility.MOSTLY),
        "register": verdict.register_appropriate,
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    return DeliveryResult(passed=not failed, failed_criteria=failed)


class PresentationCoach:
    def __init__(self, gateway: LLMGateway, explanation_workers: int = 4) -> None:
        # Decks are accepted only behind the "public content" checkbox and the
        # do-not-upload-work-data note (decision 2), so these tasks are PUBLIC.
        self._run = partial(
            gateway.generate_validated,
            data_class=DataClass.PUBLIC,
            prompt_version=prompts.PROMPT_VERSION,
        )
        self._explanation_workers = max(1, explanation_workers)

    def localize_deck(
        self,
        slides: Sequence[SlideInput],
        context: Mapping[str, str],
        profile: ProfileRecord | None = None,
    ) -> LocalizedDeck:
        """Localize each slide in parallel, then review the running order once."""

        if not slides:
            raise GenerationError("Add at least one slide before localizing.")
        localizations = self._localize_slides(slides, context)
        flow_review, _ = self._run(
            DeckFlowReview,
            prompts.deck_flow_system_prompt(context),
            prompts.deck_flow_user_prompt(slides),
            "deck_flow",
            "We could not review the deck flow. Please retry.",
            lambda response: response,
        )
        provider_name = localizations[0][1]
        return LocalizedDeck(
            tuple(package for package, _ in localizations), flow_review, provider_name
        )

    def _localize_slides(
        self, slides: Sequence[SlideInput], context: Mapping[str, str]
    ) -> list[tuple[SlideLocalization, str]]:
        system_prompt = prompts.slide_localize_system_prompt(context)
        workers = min(self._explanation_workers, max(1, len(slides)))
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="slide-localize")
        try:
            futures = [
                pool.submit(
                    self._run,
                    SlideLocalization,
                    system_prompt,
                    prompts.slide_localize_user_prompt(slide),
                    "slide_localize",
                    "We could not localize a slide. Please retry.",
                    lambda response: response,
                )
                for slide in slides
            ]
            # Ordered assembly: results are read back in submission order, so a
            # slide that finishes early still lands in its own position.
            return [future.result() for future in futures]
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def coach_deck_delivery(
        self,
        slides: Sequence[SlideInput],
        context: Mapping[str, str],
        profile: ProfileRecord | None = None,
    ) -> CoachedDeck:
        """Coach how to deliver each slide, generated in parallel and kept in order."""

        if not slides:
            raise GenerationError("Add at least one slide before practicing delivery.")
        system_prompt = prompts.delivery_coach_system_prompt(context)
        workers = min(self._explanation_workers, max(1, len(slides)))
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="delivery-coach")
        try:
            total = len(slides)
            futures = [
                pool.submit(
                    self._run,
                    SlideDeliveryCoaching,
                    system_prompt,
                    prompts.delivery_coach_user_prompt(slide, index + 1, total),
                    "delivery_coach",
                    "We could not prepare delivery coaching for a slide. Please retry.",
                    lambda response: response,
                )
                for index, slide in enumerate(slides)
            ]
            results = [future.result() for future in futures]
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return CoachedDeck(tuple(package for package, _ in results), results[0][1])

    def judge_delivery(
        self,
        coaching: SlideDeliveryCoaching,
        slide: SlideInput,
        learner_delivery: str,
        context: Mapping[str, str],
    ) -> DeliveryJudgement:
        """Score the learner's spoken delivery of one slide against its key message."""

        package, provider_name = self._run(
            DeliveryVerdict,
            prompts.delivery_judge_system_prompt(context),
            prompts.delivery_judge_user_prompt(coaching, slide, learner_delivery),
            "delivery_judge",
            "We could not evaluate the delivery. Please retry.",
            lambda response: response,
        )
        return DeliveryJudgement(package, provider_name)
