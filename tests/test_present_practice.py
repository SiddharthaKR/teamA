"""Tests for practice-presenting: coaching/verdict schemas, deterministic
per-slide pass, ordered parallel coaching, and per-phase routing (coaching to
the Japanese model, delivery judge to the structured model).
"""

import json
from threading import Lock

import pytest

from japanese_workplace_tutor.generation import (
    Comprehensibility,
    DeliveryVerdict,
    LessonGenerationService,
    SlideDeliveryCoaching,
    SlideInput,
    evaluate_delivery,
)


def _coaching(title: str = "Results") -> SlideDeliveryCoaching:
    return SlideDeliveryCoaching(
        key_message=f"[msg]{title}",
        spoken_script="第3四半期の売上は前年同期比で12%増加しました。",
        transition_in="続きまして、実績についてご説明します。",
        delivery_tips="Pause after the number.",
        rehearsal_options=(
            "売上は12%増加しました。",
            "売上、まあまあ伸びました。",
            "来期の予算の話をします。",
        ),
    )


def _verdict(**overrides) -> DeliveryVerdict:
    base = dict(
        covers_key_message=True,
        coverage_evidence="stated the 12% figure",
        comprehensible=Comprehensibility.MOSTLY,
        comprehensible_evidence="clear",
        register_appropriate=True,
        register_evidence="polite",
        improvement_tip="Slow down on the number.",
    )
    base.update(overrides)
    return DeliveryVerdict(**base)


def test_schemas_validate_and_reject_duplicate_options() -> None:
    assert _coaching().key_message
    assert _verdict().covers_key_message
    with pytest.raises(ValueError, match="distinct"):
        SlideDeliveryCoaching(
            key_message="m",
            spoken_script="s",
            transition_in="t",
            delivery_tips="d",
            rehearsal_options=("同じ", "同じ", "別"),
        )


@pytest.mark.parametrize(
    ("overrides", "passed", "failed"),
    (
        ({}, True, ()),
        ({"covers_key_message": False}, False, ("key message",)),
        ({"comprehensible": Comprehensibility.NO}, False, ("comprehensibility",)),
        ({"register_appropriate": False}, False, ("register",)),
        ({"comprehensible": Comprehensibility.YES}, True, ()),
    ),
)
def test_evaluate_delivery_is_deterministic(overrides, passed, failed) -> None:
    result = evaluate_delivery(_verdict(**overrides))
    assert result.passed is passed
    assert result.failed_criteria == failed


class PracticeTransport:
    """Keys coaching to the slide title; returns the verdict for judge calls."""

    def __init__(self, verdict_json: str) -> None:
        self.verdict_json = verdict_json
        self.calls: list[str] = []
        self._lock = Lock()

    def generate(self, model_id, system_prompt, user_prompt, response_schema=None, timeout_seconds=None):
        with self._lock:
            self.calls.append(model_id)
        if "<delivery_data>" in user_prompt:
            return self.verdict_json
        data = json.loads(user_prompt.split("<slide>\n", 1)[1].split("\n</slide>")[0])
        return _coaching(data["title"]).model_dump_json()


def test_coach_deck_orders_slides_and_routes_each_phase() -> None:
    slides = [SlideInput("Results", "Q3 +12%"), SlideInput("Risks", "supply"), SlideInput("Next", "APAC")]
    transport = PracticeTransport(_verdict().model_dump_json())
    service = LessonGenerationService(
        transport,
        "tsuzumi2",
        "gpt-5-nano",
        quiz_primary_model="gpt-5-nano",
        quiz_fallback_model="tsuzumi2",
    )

    coached = service.coach_deck_delivery(slides, {"audience": "executive"})
    assert [c.key_message for c in coached.slides] == ["[msg]Results", "[msg]Risks", "[msg]Next"]
    assert transport.calls.count("tsuzumi2") == 3  # coaching on the Japanese model
    assert coached.provider_name == "Tsuzumi 2"

    judged = service.judge_delivery(
        coached.slides[0], slides[0], "第3四半期の売上は12%増加しました。", {"audience": "executive"}
    )
    assert judged.provider_name == "GPT-5 nano"  # judge routed to the structured model
    assert transport.calls.count("gpt-5-nano") == 1


def test_coach_deck_rejects_empty() -> None:
    from japanese_workplace_tutor.generation import GenerationError

    service = LessonGenerationService(PracticeTransport("{}"), "tsuzumi2", "gpt-5-nano")
    with pytest.raises(GenerationError):
        service.coach_deck_delivery([], {})
