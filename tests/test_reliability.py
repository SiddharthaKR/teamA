"""Reliability-hardening tests: tolerant transport, self-checking answer keys,
and per-phase model routing. Kept separate from the large existing suites and
reuses their fixtures via ``test_generation``.
"""

import json

import pytest
import requests

from japanese_workplace_tutor.generation import (
    LessonGenerationService,
    OpenAICompatibleTransport,
    ScenarioMode,
    extract_json_text,
)
from japanese_workplace_tutor.lesson import FixtureQuestion, QuestionForm

from test_generation import (
    FakeTransport,
    conversation_payload,
    conversation_quiz_payload,
    profile,
)


# --------------------------------------------------------------------------- #
# extract_json_text — recover JSON from noisy model output
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ("Sure! Here it is: {\"a\": 1} — hope that helps", '{"a": 1}'),
        ('{"a": 1}', '{"a": 1}'),
        ("[1, 2, 3]", "[1, 2, 3]"),
        ("no json here at all", "no json here at all"),
    ),
)
def test_extract_json_text_recovers_the_json_span(raw: str, expected: str) -> None:
    assert extract_json_text(raw) == expected


# --------------------------------------------------------------------------- #
# Self-checking answer key — resolve the correct index from the option's text
# --------------------------------------------------------------------------- #
def test_correct_value_resolves_the_index_regardless_of_order() -> None:
    question = FixtureQuestion(
        question_id="q1",
        item_id="x",
        form=QuestionForm.MEANING,
        prompt="What does 仕様 mean?",
        options=("Schedule", "Specification", "Meeting", "Report"),
        correct_value="Specification",
        explanation="仕様 means specification.",
    )
    assert question.correct_option_index == 1
    # The self-checking key never leaks into a serialized dump.
    assert "correct_value" not in question.model_dump()


def test_correct_value_overrides_a_miscounted_index() -> None:
    question = FixtureQuestion(
        question_id="q2",
        item_id="x",
        form=QuestionForm.MEANING,
        prompt="p",
        options=("A", "B", "C", "D"),
        correct_option_index=0,  # the model miscounted
        correct_value="C",
        explanation="e",
    )
    assert question.correct_option_index == 2


def test_correct_value_that_matches_no_option_is_rejected() -> None:
    with pytest.raises(ValueError, match="correct_value"):
        FixtureQuestion(
            question_id="q3",
            item_id="x",
            form=QuestionForm.MEANING,
            prompt="p",
            options=("A", "B", "C", "D"),
            correct_value="Z",
            explanation="e",
        )


def test_generated_quiz_accepts_value_keyed_answers() -> None:
    """A quiz whose questions carry only correct_value (no index) still validates."""

    payload = conversation_quiz_payload()
    for question in (*payload["questions"], *payload["retry_questions"]):
        question["correct_value"] = question["options"][question["correct_option_index"]]
        del question["correct_option_index"]
    transport = FakeTransport(
        [json.dumps(conversation_payload()), json.dumps(payload)]
    )
    service = LessonGenerationService(transport, "tsuzumi-id", "gpt-id")

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )
    quiz = service.generate_quiz(draft.content)

    for question in quiz.questions:
        assert 0 <= question.correct_option_index <= 3


# --------------------------------------------------------------------------- #
# Per-phase model routing — quiz to the structured model, Japanese to primary
# --------------------------------------------------------------------------- #
def test_quiz_phase_routes_to_the_configured_quiz_model() -> None:
    transport = FakeTransport(
        [json.dumps(conversation_payload()), json.dumps(conversation_quiz_payload())]
    )
    service = LessonGenerationService(
        transport,
        "tsuzumi-id",
        "gpt-id",
        quiz_primary_model="gpt-id",
        quiz_fallback_model="tsuzumi-id",
    )

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )
    # The Japanese-generation phase still uses the global primary (Tsuzumi).
    assert transport.calls == ["tsuzumi-id"]
    assert draft.provider_name == "Tsuzumi 2"

    quiz = service.generate_quiz(draft.content)
    # The quiz phase is routed to the structured model first.
    assert transport.calls == ["tsuzumi-id", "gpt-id"]
    assert quiz.provider_name == "GPT-5 nano"


def test_quiz_phase_defaults_to_the_global_models_when_unset() -> None:
    transport = FakeTransport(
        [json.dumps(conversation_payload()), json.dumps(conversation_quiz_payload())]
    )
    service = LessonGenerationService(transport, "tsuzumi-id", "gpt-id")

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )
    quiz = service.generate_quiz(draft.content)

    assert transport.calls == ["tsuzumi-id", "tsuzumi-id"]
    assert quiz.provider_name == "Tsuzumi 2"


# --------------------------------------------------------------------------- #
# Tolerant transport — degrade strict json_schema to json_object on a 4xx
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, status_code: int, content: str) -> None:
        self.status_code = status_code
        self._content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self  # type: ignore[attr-defined]
            raise error

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.payloads: list[dict[str, object]] = []

    def post(self, url, headers=None, json=None, timeout=None):  # noqa: A002
        self.payloads.append(json)
        return self._responses.pop(0)


def test_transport_degrades_to_json_object_when_schema_is_rejected() -> None:
    transport = OpenAICompatibleTransport("https://proxy.example/v1", "secret")
    transport._session = _FakeSession(  # type: ignore[assignment]
        [_FakeResponse(400, ""), _FakeResponse(200, '```json\n{"ok": 1}\n```')]
    )

    result = transport.generate(
        "tsuzumi2", "system prompt", "user prompt", {"type": "object", "properties": {}}
    )

    assert result == '{"ok": 1}'  # fence stripped by extract_json_text
    first, second = transport._session.payloads  # type: ignore[attr-defined]
    # First attempt used strict schema; the degraded retry dropped it for json_object
    # and described the schema in the prompt instead.
    assert first["response_format"]["type"] == "json_schema"
    assert second["response_format"] == {"type": "json_object"}
    assert "does not support schema-constrained output" in second["messages"][0]["content"]


def test_transport_reraises_non_4xx_errors() -> None:
    transport = OpenAICompatibleTransport("https://proxy.example/v1", "secret")
    transport._session = _FakeSession([_FakeResponse(500, "")])  # type: ignore[assignment]

    with pytest.raises(requests.HTTPError):
        transport.generate(
            "tsuzumi2", "system", "user", {"type": "object", "properties": {}}
        )
