"""The single path every model call takes: routing, validation, repair, fallback.

Features hand the gateway a response schema, prompts and a finalize step. The
gateway owns which model runs, retries, hedging and failure handling; it never
decides learning outcomes. Every call is tagged with a DataClass, and PRIVATE
content is refused unless the transport is an on-premises one.
"""

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
import json
import logging
from time import monotonic
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..core.errors import GenerationError
from ..core.ports import DataClass, ModelTransport, accepts_private_data

LOGGER = logging.getLogger("japanese_workplace_tutor.generation")
PackageT = TypeVar("PackageT")


@dataclass(frozen=True)
class _HedgeOutcome:
    package: object | None
    provider_name: str | None
    repair_feedback: str
    skip_primary_repair: bool


@dataclass(frozen=True)
class _AttemptOutcome:
    provider_name: str
    model_id: str
    started: float
    fallback_reason: str | None
    package: object | None
    error: Exception | None


def provider_label(model_id: str) -> str:
    """Human-facing provider name derived from the model id.

    Deriving the label from the model (rather than hard-coding it beside each
    attempt) lets per-phase routing swap which model is primary while the shown
    provider name stays correct automatically.
    """

    if model_id.lower().startswith("mock"):
        return "Mock (offline fixtures)"
    return "GPT-5 nano" if "gpt" in model_id.lower() else "Tsuzumi 2"


class LLMGateway:
    def __init__(
        self,
        transport: ModelTransport,
        primary_model: str,
        fallback_model: str,
        primary_timeout_seconds: float | None = None,
        hedge_after_seconds: float | None = None,
        quiz_primary_model: str | None = None,
        quiz_fallback_model: str | None = None,
    ) -> None:
        self._transport = transport
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._primary_timeout_seconds = primary_timeout_seconds
        self._hedge_after_seconds = hedge_after_seconds
        # Per-phase routing: the primary is strong at Japanese generation but weak at
        # strict quiz JSON, so a deployment may route the quiz phase to a different,
        # more structured model. Defaults to the global models, preserving the plain
        # primary-then-fallback behavior when unset.
        self._quiz_primary_model = quiz_primary_model or primary_model
        self._quiz_fallback_model = quiz_fallback_model or fallback_model

    def _phase_models(self, phase: str) -> tuple[str, str]:
        """Return (primary_model, fallback_model) for a generation phase."""

        if phase in ("quiz", "roleplay_judge", "deck_flow", "delivery_judge"):
            return self._quiz_primary_model, self._quiz_fallback_model
        return self._primary_model, self._fallback_model

    def _generate_validated(
        self,
        response_type: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        phase: str,
        failure_message: str,
        finalize: Callable[[BaseModel], PackageT],
    ) -> tuple[PackageT, str]:
        repair_feedback = "The previous request failed before producing valid JSON."
        skip_primary_repair = False
        primary_model, fallback_model = self._phase_models(phase)
        attempts = (
            (
                provider_label(primary_model),
                primary_model,
                1,
                None,
                False,
                self._primary_timeout_seconds,
            ),
            (
                provider_label(primary_model),
                primary_model,
                2,
                "primary_retry",
                True,
                self._primary_timeout_seconds,
            ),
            (provider_label(fallback_model), fallback_model, 1, "primary_failed", False, None),
            (provider_label(fallback_model), fallback_model, 2, "fallback_retry", True, None),
        )
        if self._hedge_after_seconds is not None:
            hedged = self._race_first_attempts(
                response_type, system_prompt, user_prompt, phase, finalize
            )
            if hedged.package is not None and hedged.provider_name is not None:
                return hedged.package, hedged.provider_name
            repair_feedback = hedged.repair_feedback
            skip_primary_repair = hedged.skip_primary_repair
            attempts = tuple(attempt for attempt in attempts if attempt[4])
        for (
            provider_name,
            model_id,
            attempt,
            fallback_reason,
            is_repair,
            timeout_seconds,
        ) in attempts:
            if model_id == primary_model and is_repair and skip_primary_repair:
                continue
            started = monotonic()
            try:
                raw_response = self._transport.generate(
                    model_id,
                    system_prompt,
                    self._repair_prompt(user_prompt, repair_feedback)
                    if is_repair
                    else user_prompt,
                    response_type.model_json_schema(),
                    timeout_seconds,
                )
                package = finalize(
                    response_type.model_validate(json.loads(raw_response))
                )
            except (Exception, json.JSONDecodeError) as error:
                repair_feedback = self._safe_repair_feedback(error)
                is_validation_failure = isinstance(
                    error, (ValidationError, ValueError, KeyError, TypeError)
                )
                if model_id == primary_model and not is_repair:
                    skip_primary_repair = not is_validation_failure
                self._log_attempt(
                    provider_name,
                    model_id,
                    attempt,
                    "failed",
                    started,
                    f"{phase}:{fallback_reason or ('validation_failure' if is_validation_failure else 'technical_failure')}",
                )
                continue
            self._log_attempt(
                provider_name,
                model_id,
                attempt,
                "success",
                started,
                f"{phase}:{fallback_reason or 'none'}",
            )
            return package, provider_name
        raise GenerationError(failure_message) from None

    def _race_first_attempts(
        self,
        response_type: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        phase: str,
        finalize: Callable[[BaseModel], PackageT],
    ) -> _HedgeOutcome:
        """Start the fallback beside a slow primary so one stalled route cannot own the request."""

        primary_model, fallback_model = self._phase_models(phase)

        def run(
            provider_name: str,
            model_id: str,
            fallback_reason: str | None,
            timeout_seconds: float | None,
        ) -> _AttemptOutcome:
            started = monotonic()
            try:
                raw_response = self._transport.generate(
                    model_id,
                    system_prompt,
                    user_prompt,
                    response_type.model_json_schema(),
                    timeout_seconds,
                )
                package = finalize(
                    response_type.model_validate(json.loads(raw_response))
                )
            except (Exception, json.JSONDecodeError) as error:
                return _AttemptOutcome(
                    provider_name, model_id, started, fallback_reason, None, error
                )
            return _AttemptOutcome(
                provider_name, model_id, started, fallback_reason, package, None
            )

        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hedged-generation")
        repair_feedback = "The previous request failed before producing valid JSON."
        skip_primary_repair = False
        try:
            pending = {
                pool.submit(
                    run,
                    provider_label(primary_model),
                    primary_model,
                    None,
                    self._primary_timeout_seconds,
                )
            }
            hedged = False
            while pending:
                done, pending = wait(
                    pending,
                    timeout=None if hedged else self._hedge_after_seconds,
                    return_when=FIRST_COMPLETED,
                )
                if not done and not hedged:
                    pending.add(
                        pool.submit(
                            run,
                            provider_label(fallback_model),
                            fallback_model,
                            "primary_hedged",
                            None,
                        )
                    )
                    hedged = True
                    continue
                for future in done:
                    outcome = future.result()
                    if outcome.package is not None:
                        self._log_attempt(
                            outcome.provider_name,
                            outcome.model_id,
                            1,
                            "success",
                            outcome.started,
                            f"{phase}:{outcome.fallback_reason or 'none'}",
                        )
                        return _HedgeOutcome(
                            outcome.package,
                            outcome.provider_name,
                            repair_feedback,
                            False,
                        )
                    error = outcome.error
                    assert error is not None
                    repair_feedback = self._safe_repair_feedback(error)
                    is_validation_failure = isinstance(
                        error, (ValidationError, ValueError, KeyError, TypeError)
                    )
                    if outcome.model_id == primary_model:
                        skip_primary_repair = not is_validation_failure
                    self._log_attempt(
                        outcome.provider_name,
                        outcome.model_id,
                        1,
                        "failed",
                        outcome.started,
                        f"{phase}:{outcome.fallback_reason or ('validation_failure' if is_validation_failure else 'technical_failure')}",
                    )
                    if outcome.model_id == primary_model and not hedged:
                        pending.add(
                            pool.submit(
                                run,
                                provider_label(fallback_model),
                                fallback_model,
                                "primary_failed",
                                None,
                            )
                        )
                        hedged = True
            return _HedgeOutcome(None, None, repair_feedback, skip_primary_repair)
        finally:
            # A losing route is abandoned rather than awaited; that is the point of hedging.
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _log_attempt(
        provider_name: str,
        model_id: str,
        attempt: int,
        status: str,
        started: float,
        fallback_reason: str | None,
    ) -> None:
        LOGGER.info(
            "model_attempt provider=%s model=%s attempt=%s status=%s latency_ms=%s fallback_reason=%s",
            provider_name,
            model_id,
            attempt,
            status,
            round((monotonic() - started) * 1000),
            fallback_reason or "none",
        )

    @staticmethod
    def _repair_prompt(original_prompt: str, repair_feedback: str) -> str:
        return (
            f"{original_prompt}\n\nThe previous attempt was rejected. {repair_feedback} "
            "Generate a new complete JSON object and follow every schema rule exactly."
        )

    @staticmethod
    def _safe_repair_feedback(error: Exception) -> str:
        if isinstance(error, ValidationError):
            error_items = error.errors()
            messages = (
                f"{'.'.join(str(part) for part in item['loc']) or 'root'}: {item['msg']}"
                for item in error_items[:12]
            )
            suffix = (
                f"; and {len(error_items) - 12} additional schema errors"
                if len(error_items) > 12
                else ""
            )
            return "Fix these validation errors: " + "; ".join(messages) + suffix
        if isinstance(error, json.JSONDecodeError):
            return "The response was not valid JSON."
        return "The provider request failed before producing a valid lesson."

    def generate_validated(
        self,
        response_type: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        phase: str,
        failure_message: str,
        finalize: Callable[[BaseModel], PackageT],
        *,
        data_class: DataClass,
        prompt_version: str,
    ) -> tuple[PackageT, str]:
        """Run one tagged task; refuse PRIVATE content on a transport that may not see it."""

        if data_class is DataClass.PRIVATE and not accepts_private_data(self._transport):
            raise GenerationError(
                "This content stays on the company network, and no on-premises model is "
                "configured yet."
            )
        LOGGER.info(
            "model_task phase=%s prompt_version=%s data_class=%s",
            phase,
            prompt_version,
            data_class.value,
        )
        return self._generate_validated(
            response_type, system_prompt, user_prompt, phase, failure_message, finalize
        )
