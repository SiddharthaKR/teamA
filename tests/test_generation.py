import json
import logging
from pathlib import Path
import sqlite3
from threading import Lock
from time import sleep

import pytest

from japanese_workplace_tutor.auth import AuthenticationService
from japanese_workplace_tutor.database import create_database_engine
from japanese_workplace_tutor.generation import (
    GenerationError,
    GeneratedLessonContentPackage,
    GeneratedQuizPackage,
    LessonGenerationService,
    ScenarioInput,
    ScenarioMode,
    detect_scenario_mode,
    expected_line_count,
)
from japanese_workplace_tutor.features.lessons import LessonGenerator, canonical_item_id
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit
from japanese_workplace_tutor.lesson import LessonService
from japanese_workplace_tutor.prompts import lessons as lesson_prompts
from japanese_workplace_tutor.schemas.lessons import validate_explanations
from japanese_workplace_tutor.lesson import ItemCategory, ProgressRecord
from japanese_workplace_tutor.profile import JapaneseLevel, ProfileRecord, LevelSource
from japanese_workplace_tutor.settings import Settings


VALID_PAYLOAD = {
    "lesson": {
        "topic_id": "scenario-requirements-01",
        "title": "仕様の確認 — Confirming a Requirement",
        "difficulty": "JLPT N4",
        "passage": (
            "山田さん: 仕様について確認してもよろしいでしょうか。\n"
            "アレックスさん: はい、日程も確認します。\n"
            "山田さん: では、会議で共有してください。\n"
            "アレックスさん: 午後に結果を報告します。\n"
            "山田さん: 資料も準備できますか。\n"
            "アレックスさん: はい、午前中に準備します。\n"
            "山田さん: 分からない点は聞いてください。\n"
            "アレックスさん: ありがとうございます。\n"
            "山田さん: では、よろしくお願いします。\n"
            "アレックスさん: はい、よろしくお願いします。"
        ),
        "items": [
            {
                "canonical_id": "vocabulary:shiyou",
                "category": "vocabulary",
                "expression": "仕様",
                "reading": "しよう",
                "meaning": "specification",
                "example": "仕様を確認します。",
                "jlpt_level": "JLPT N3",
                "jlpt_provenance": "model-estimate",
                "jlpt_confidence": 0.7,
            },
            {
                "canonical_id": "vocabulary:kakunin-generated",
                "category": "vocabulary",
                "expression": "確認",
                "reading": "かくにん",
                "meaning": "confirmation",
                "example": "日程を確認します。",
                "jlpt_level": "JLPT N4",
                "jlpt_provenance": "model-estimate",
                "jlpt_confidence": 0.8,
            },
            {
                "canonical_id": "grammar:temo-yoroshii-generated",
                "category": "grammar",
                "expression": "〜てもよろしいでしょうか",
                "reading": "〜てもよろしいでしょうか",
                "meaning": "May I ...?",
                "example": "質問してもよろしいでしょうか。",
                "jlpt_level": "JLPT N3",
                "jlpt_provenance": "model-estimate",
                "jlpt_confidence": 0.7,
            },
        ],
        "questions": [
            {
                "question_id": "q-spec-meaning",
                "item_id": "vocabulary:shiyou",
                "form": "meaning",
                "prompt": "What does 仕様 mean?",
                "options": ["Specification", "Schedule", "Meeting", "Report"],
                "correct_option_index": 0,
                "explanation": "仕様 means specification.",
            },
            {
                "question_id": "q-confirm-reading",
                "item_id": "vocabulary:kakunin-generated",
                "form": "reading",
                "prompt": "How is 確認 read?",
                "options": ["かくにん", "かくじん", "こうにん", "こうじん"],
                "correct_option_index": 0,
                "explanation": "確認 is read かくにん.",
            },
            {
                "question_id": "q-permission-cloze",
                "item_id": "grammar:temo-yoroshii-generated",
                "form": "contextual_cloze",
                "prompt": "Choose the polite request: 確認し___。",
                "options": ["てもよろしいでしょうか", "てはいけません", "ながら", "そうです"],
                "correct_option_index": 0,
                "explanation": "The phrase politely asks permission.",
            },
            {
                "question_id": "q-confirm-meaning",
                "item_id": "vocabulary:kakunin-generated",
                "form": "meaning",
                "prompt": "What does 確認する mean?",
                "options": ["To confirm", "To reject", "To send", "To finish"],
                "correct_option_index": 0,
                "explanation": "確認する means to confirm or check.",
            },
        ],
        "recap": "Use 仕様 and 確認 to clarify requirements politely.",
    },
    "line_explanations": [
        {
            "japanese_text": "山田さん: 仕様について確認してもよろしいでしょうか。",
            "english_meaning": "Manager: May I confirm the specification?",
            "kanji": [
                {
                    "expression": "仕様",
                    "reading": "しよう",
                    "meaning": "specification",
                    "explanation": "A work specification or requirement.",
                }
            ],
            "vocabulary": [
                {
                    "expression": "仕様",
                    "reading": "しよう",
                    "meaning": "specification",
                    "explanation": "The subject being confirmed.",
                }
            ],
            "grammar": [
                {
                    "expression": "〜てもよろしいでしょうか",
                    "reading": "〜てもよろしいでしょうか",
                    "meaning": "May I ...?",
                    "explanation": "A polite request for permission.",
                }
            ],
        },
        {
            "japanese_text": "アレックスさん: はい、日程も確認します。",
            "english_meaning": "Me: Yes, I will also confirm the schedule.",
            "kanji": [],
            "vocabulary": [
                {
                    "expression": "確認",
                    "reading": "かくにん",
                    "meaning": "confirmation",
                    "explanation": "確認します means to check or confirm.",
                }
            ],
            "grammar": [],
        },
        {
            "japanese_text": "山田さん: では、会議で共有してください。",
            "english_meaning": "Manager: Then, please share it at the meeting.",
            "kanji": [],
            "vocabulary": [
                {
                    "expression": "共有",
                    "reading": "きょうゆう",
                    "meaning": "sharing",
                    "explanation": "共有する means to share information.",
                }
            ],
            "grammar": [],
        },
        {
            "japanese_text": "アレックスさん: 午後に結果を報告します。",
            "english_meaning": "Me: I will report the result in the afternoon.",
            "kanji": [],
            "vocabulary": [
                {
                    "expression": "報告",
                    "reading": "ほうこく",
                    "meaning": "report",
                    "explanation": "報告する means to report information.",
                }
            ],
            "grammar": [],
        },
        {
            "japanese_text": "山田さん: 資料も準備できますか。",
            "english_meaning": "Yamada: Can you also prepare the materials?",
            "kanji": [],
            "vocabulary": [{"expression": "資料", "reading": "しりょう", "meaning": "materials", "explanation": "資料 refers to meeting documents."}],
            "grammar": [],
        },
        {
            "japanese_text": "アレックスさん: はい、午前中に準備します。",
            "english_meaning": "Alex: Yes, I will prepare them during the morning.",
            "kanji": [],
            "vocabulary": [{"expression": "準備", "reading": "じゅんび", "meaning": "preparation", "explanation": "準備します means to prepare."}],
            "grammar": [],
        },
        {
            "japanese_text": "山田さん: 分からない点は聞いてください。",
            "english_meaning": "Yamada: Please ask about anything you do not understand.",
            "kanji": [],
            "vocabulary": [{"expression": "聞く", "reading": "きく", "meaning": "to ask", "explanation": "Here 聞く means to ask a question."}],
            "grammar": [],
        },
        {
            "japanese_text": "アレックスさん: ありがとうございます。",
            "english_meaning": "Alex: Thank you.",
            "kanji": [],
            "vocabulary": [{"expression": "ありがとうございます", "reading": "ありがとうございます", "meaning": "thank you", "explanation": "A polite expression of thanks."}],
            "grammar": [],
        },
        {
            "japanese_text": "山田さん: では、よろしくお願いします。",
            "english_meaning": "Yamada: Well then, thank you in advance.",
            "kanji": [],
            "vocabulary": [{"expression": "よろしくお願いします", "reading": "よろしくおねがいします", "meaning": "thank you in advance", "explanation": "A conventional polite closing request."}],
            "grammar": [],
        },
        {
            "japanese_text": "アレックスさん: はい、よろしくお願いします。",
            "english_meaning": "Alex: Yes, thank you in advance.",
            "kanji": [],
            "vocabulary": [{"expression": "よろしくお願いします", "reading": "よろしくおねがいします", "meaning": "thank you in advance", "explanation": "It closes the exchange politely."}],
            "grammar": [],
        },
    ],
    "retry_questions": [
        {
            "question_id": "retry-spec-cloze",
            "item_id": "vocabulary:shiyou",
            "form": "contextual_cloze",
            "prompt": "Choose the word for specification: ___を確認します。",
            "options": ["仕様", "会議", "報告", "予定"],
            "correct_option_index": 0,
            "explanation": "仕様 is the specification being checked.",
        },
        {
            "question_id": "retry-confirm-cloze",
            "item_id": "vocabulary:kakunin-generated",
            "form": "contextual_cloze",
            "prompt": "Choose the checking action: 日程を___します。",
            "options": ["確認", "報告", "共有", "変更"],
            "correct_option_index": 0,
            "explanation": "確認します means check or confirm.",
        },
        {
            "question_id": "retry-permission-meaning",
            "item_id": "grammar:temo-yoroshii-generated",
            "form": "meaning",
            "prompt": "What does 〜てもよろしいでしょうか do?",
            "options": ["Asks permission", "Forbids action", "Reports news", "Compares choices"],
            "correct_option_index": 0,
            "explanation": "It is a polite permission request.",
        },
        {
            "question_id": "retry-confirm-reading",
            "item_id": "vocabulary:kakunin-generated",
            "form": "reading",
            "prompt": "Select the reading for 確認.",
            "options": ["かくにん", "かくじん", "こうにん", "こうじん"],
            "correct_option_index": 0,
            "explanation": "The reading is かくにん.",
        },
    ],
}


class FakeTransport:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.calls: list[str] = []
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []
        self.timeouts: list[float | None] = []

    def generate(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        self.calls.append(model_id)
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        self.timeouts.append(timeout_seconds)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return {"choices": [{"message": {"content": "{}"}}]}


def profile(level: JapaneseLevel = JapaneseLevel.N3) -> ProfileRecord:
    return ProfileRecord(
        user_id=1,
        role="Software engineer",
        tasks=("Discuss requirements",),
        tools_domain=None,
        declared_level=level,
        estimated_working_level=None,
        level_source=LevelSource.SELF_REPORTED,
        level_confidence=1.0,
        romaji_preference=False,
    )


def generator(transport: FakeTransport) -> LessonGenerationService:
    return LessonGenerationService(
        transport, "tsuzumi-id", "gpt-id", primary_timeout_seconds=45.0
    )


class HedgeTransport:
    """Thread-safe fake with per-model delays, so hedging can be exercised deterministically."""

    def __init__(self, responses: dict[str, tuple[float, object]]) -> None:
        self.responses = responses
        self.calls: list[str] = []
        self._lock = Lock()

    def generate(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        with self._lock:
            self.calls.append(model_id)
        delay, response = self.responses[model_id]
        sleep(delay)
        if isinstance(response, Exception):
            raise response
        return str(response)


def test_transport_uses_low_reasoning_only_for_gpt5_models() -> None:
    from unittest.mock import Mock

    from japanese_workplace_tutor.generation import OpenAICompatibleTransport

    transport = OpenAICompatibleTransport("https://proxy.example/v1", "secret")
    post = Mock(return_value=FakeResponse())
    transport._session.post = post

    transport.generate("gpt-5-nano", "system", "user")
    gpt_payload = post.call_args.kwargs["json"]
    assert gpt_payload["reasoning_effort"] == "low"

    transport.generate(
        "gpt-5-nano", "system", "user", {"type": "object", "properties": {}}
    )
    structured_payload = post.call_args.kwargs["json"]
    assert structured_payload["response_format"]["type"] == "json_schema"
    assert structured_payload["response_format"]["json_schema"]["strict"] is True

    transport.generate("tsuzumi2", "system", "user")
    tsuzumi_payload = post.call_args.kwargs["json"]
    assert "reasoning_effort" not in tsuzumi_payload


def content_payload() -> dict[str, object]:
    payload = json.loads(json.dumps(VALID_PAYLOAD))
    payload["lesson"].pop("questions")
    payload.pop("retry_questions")
    return payload


DIALOGUE_TEXTS = (
    "仕様について確認してもよろしいでしょうか。",
    "はい、日程も確認します。",
    "では、会議で共有してください。",
    "午後に結果を報告します。",
    "資料も準備できますか。",
    "はい、午前中に準備します。",
    "分からない点は聞いてください。",
    "ありがとうございます。",
    "では、よろしくお願いします。",
    "はい、よろしくお願いします。",
)
TOOLKIT = SudachiToolkit.shared()
TARGET_ITEM_IDS = tuple(
    canonical_item_id(category, expression, TOOLKIT)
    for category, expression in (
        (ItemCategory.VOCABULARY, "仕様"),
        (ItemCategory.GRAMMAR, "〜てもよろしいでしょうか"),
        (ItemCategory.VOCABULARY, "確認"),
    )
)


def language_point(
    expression: str, reading: str, meaning: str, *, is_quiz_target: bool = False
) -> dict[str, object]:
    return {
        "expression": expression,
        "reading": reading,
        "meaning": meaning,
        "explanation": f"Use {expression} when you mean {meaning}.",
        "jlpt_level": "JLPT N4",
        "is_quiz_target": is_quiz_target,
    }


def generated_line(index: int, japanese_text: str) -> dict[str, object]:
    return {
        "japanese_text": japanese_text,
        "english_meaning": f"English meaning of line {index + 1}.",
        "kanji": [],
        "vocabulary": [
            language_point("仕様", "しよう", "specification", is_quiz_target=index == 0)
            if index == 0
            else language_point(
                "確認", "かくにん", "confirmation", is_quiz_target=index == 1
            )
        ],
        "grammar": [
            language_point(
                "〜てもよろしいでしょうか",
                "〜てもよろしいでしょうか",
                "May I ...?",
                is_quiz_target=index == 0,
            )
            if index == 0
            else language_point("〜ます", "〜ます", "polite present form")
        ],
    }


def conversation_payload() -> dict[str, object]:
    return {
        "topic_id": VALID_PAYLOAD["lesson"]["topic_id"],
        "japanese_title": "仕様の確認",
        "english_title": "Confirming a Requirement",
        "difficulty": "JLPT N4",
        "recap": VALID_PAYLOAD["lesson"]["recap"],
        "japanese_speaker_name": "山田",
        "other_speaker_name": "アレックス",
        "lines": [
            generated_line(index, text) for index, text in enumerate(DIALOGUE_TEXTS)
        ],
    }


def quiz_payload() -> dict[str, object]:
    return json.loads(
        json.dumps(
            {
                "questions": VALID_PAYLOAD["lesson"]["questions"],
                "retry_questions": VALID_PAYLOAD["retry_questions"],
            }
        )
    )


def conversation_quiz_payload() -> dict[str, object]:
    payload = quiz_payload()
    # Map by expression, not position: the item order differs between the two
    # payloads, and code verification caught questions attached to the wrong item.
    remapped = {
        item["canonical_id"]: canonical_item_id(
            ItemCategory(item["category"]), item["expression"], TOOLKIT
        )
        for item in VALID_PAYLOAD["lesson"]["items"]
    }
    for question in (*payload["questions"], *payload["retry_questions"]):
        question["item_id"] = remapped[question["item_id"]]
    return payload


def test_mode_detection_and_direct_tsuzumi_success(caplog: pytest.LogCaptureFixture) -> None:
    transport = FakeTransport([json.dumps(conversation_payload())])
    generation_logger = logging.getLogger("japanese_workplace_tutor.generation")
    generation_logger.disabled = False
    generation_logger.propagate = True
    caplog.set_level(logging.INFO, logger=generation_logger.name)

    result = generator(transport).generate_lesson_content(
        "I need to clarify a software requirement", ScenarioMode.GENERATE, profile()
    )

    assert detect_scenario_mode("会議の日程を確認したいです") is ScenarioMode.EXPLAIN
    assert detect_scenario_mode("Prepare for a customer call") is ScenarioMode.GENERATE
    assert result.provider_name == "Tsuzumi 2"
    assert transport.calls == ["tsuzumi-id"]
    assert "Tsuzumi 2" in caplog.text
    assert "prompt_version=lessons-v1 data_class=public" in caplog.text
    assert "clarify a software requirement" not in caplog.text


def test_content_and_quiz_are_generated_as_independent_grounded_packages() -> None:
    transport = FakeTransport(
        [json.dumps(conversation_payload()), json.dumps(conversation_quiz_payload())]
    )
    service = generator(transport)

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.content.title == VALID_PAYLOAD["lesson"]["title"]
    assert draft.content.passage == VALID_PAYLOAD["lesson"]["passage"]
    assert tuple(item.canonical_id for item in draft.content.items) == TARGET_ITEM_IDS
    assert transport.calls == ["tsuzumi-id"]
    assert "Do not generate quiz questions" in transport.system_prompts[0]

    quiz = service.generate_quiz(draft.content)

    assert len(quiz.questions) == 4
    assert quiz.provider_name == "Tsuzumi 2"
    assert transport.calls == ["tsuzumi-id", "tsuzumi-id"]
    assert "validated Japanese lesson data" in transport.system_prompts[1]
    assert TARGET_ITEM_IDS[0] in transport.user_prompts[1]


def test_split_contracts_reject_missing_lines_and_unknown_quiz_items() -> None:
    invalid_content = content_payload()
    invalid_content["line_explanations"].pop()
    content_package = GeneratedLessonContentPackage.model_validate(invalid_content)
    scenario_input = ScenarioInput(
        scenario="Clarify a requirement", mode=ScenarioMode.GENERATE
    )
    content_package = LessonGenerator._normalized_content_package(
        content_package, scenario_input
    )
    with pytest.raises(ValueError, match="exactly 10 dialogue lines"):
        LessonGenerator._validate_content_mode(
            content_package, scenario_input
        )

    invalid_quiz = quiz_payload()
    invalid_quiz["questions"][0]["item_id"] = "missing:item"
    invalid_quiz["retry_questions"][0]["item_id"] = "missing:item"
    package = GeneratedQuizPackage.model_validate(invalid_quiz)
    draft = GeneratedLessonContentPackage.model_validate(content_payload())
    with pytest.raises(ValueError, match="lesson target item"):
        LessonGenerator._validate_quiz_contract(package, draft.lesson)


def test_generated_passage_is_canonicalized_from_explained_dialogue_lines() -> None:
    payload = conversation_payload()
    payload["japanese_speaker_name"] = "山田さん"
    payload["lines"][0]["japanese_text"] = "山田さん: " + DIALOGUE_TEXTS[0]
    transport = FakeTransport([json.dumps(payload)])

    draft = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.content.passage == "\n".join(
        line.japanese_text for line in draft.line_explanations
    )
    assert draft.content.passage == VALID_PAYLOAD["lesson"]["passage"]


def test_target_expression_may_be_explained_under_another_language_category() -> None:
    payload = content_payload()
    payload["lesson"]["items"][0]["category"] = "kanji"

    package = GeneratedLessonContentPackage.model_validate(payload)

    assert package.lesson.items[0].expression == "仕様"


def test_split_generation_skips_primary_repair_after_technical_failure() -> None:
    transport = FakeTransport([TimeoutError(), json.dumps(conversation_payload())])

    draft = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.provider_name == "GPT-5 nano"
    assert transport.calls == ["tsuzumi-id", "gpt-id"]
    assert transport.timeouts == [45.0, None]


def test_split_generation_repairs_the_primary_before_falling_back() -> None:
    transport = FakeTransport(["not-json", json.dumps(conversation_payload())])

    draft = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.provider_name == "Tsuzumi 2"
    assert transport.calls == ["tsuzumi-id", "tsuzumi-id"]
    assert transport.timeouts == [45.0, 45.0]


def test_primary_provider_is_always_tried_first_for_every_lesson() -> None:
    payload = json.dumps(conversation_payload())
    transport = FakeTransport([TimeoutError(), payload, TimeoutError(), payload, payload])
    service = generator(transport)

    providers = [
        service.generate_lesson_content(
            "Clarify a requirement", ScenarioMode.GENERATE, profile()
        ).provider_name
        for _ in range(3)
    ]

    assert transport.calls == [
        "tsuzumi-id",
        "gpt-id",
        "tsuzumi-id",
        "gpt-id",
        "tsuzumi-id",
    ]
    assert providers == ["GPT-5 nano", "GPT-5 nano", "Tsuzumi 2"]


def test_a_primary_success_clears_earlier_failures() -> None:
    payload = json.dumps(conversation_payload())
    transport = FakeTransport([TimeoutError(), payload, payload, TimeoutError(), payload])
    service = generator(transport)

    for _ in range(3):
        service.generate_lesson_content(
            "Clarify a requirement", ScenarioMode.GENERATE, profile()
        )

    assert transport.calls == [
        "tsuzumi-id",
        "gpt-id",
        "tsuzumi-id",
        "tsuzumi-id",
        "gpt-id",
    ]


def test_primary_repair_then_gpt_fallback_for_invalid_output() -> None:
    too_short = conversation_payload()
    too_short["lines"] = too_short["lines"][:9]
    transport = FakeTransport(
        ["not-json", json.dumps(too_short), json.dumps(conversation_payload())]
    )

    result = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert result.provider_name == "GPT-5 nano"
    assert transport.calls == ["tsuzumi-id", "tsuzumi-id", "gpt-id"]


def test_gpt_validation_failure_gets_one_repair_attempt() -> None:
    japanese_english_title = conversation_payload()
    japanese_english_title["english_title"] = "仕様の確認"
    transport = FakeTransport(
        [
            "bad",
            "still bad",
            json.dumps(japanese_english_title),
            json.dumps(conversation_payload()),
        ]
    )

    result = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert result.provider_name == "GPT-5 nano"
    assert transport.calls == ["tsuzumi-id", "tsuzumi-id", "gpt-id", "gpt-id"]


def test_invalid_answer_key_is_rejected_before_rendering() -> None:
    invalid_key = quiz_payload()
    invalid_key["questions"][0]["correct_option_index"] = 4

    with pytest.raises(ValueError):
        GeneratedQuizPackage.model_validate(invalid_key)


def test_primary_repair_success_does_not_fall_back() -> None:
    transport = FakeTransport(["not-json", json.dumps(conversation_payload())])

    result = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert result.provider_name == "Tsuzumi 2"
    assert transport.calls == ["tsuzumi-id", "tsuzumi-id"]


def explain_payload(text: str) -> dict[str, object]:
    line = generated_line(0, text)
    line["vocabulary"].append(
        language_point("確認", "かくにん", "confirmation", is_quiz_target=True)
    )
    return {
        "topic_id": VALID_PAYLOAD["lesson"]["topic_id"],
        "japanese_title": "仕様の確認",
        "english_title": "Confirming a Requirement",
        "difficulty": "JLPT N4",
        "recap": VALID_PAYLOAD["lesson"]["recap"],
        "lines": [line],
    }


def test_japanese_text_scenario_generates_in_explain_mode() -> None:
    scenario = "仕様について確認してもよろしいでしょうか。"
    transport = FakeTransport([json.dumps(explain_payload(scenario))])

    result = generator(transport).generate_lesson_content(
        scenario, detect_scenario_mode(scenario), profile()
    )

    assert result.provider_name == "Tsuzumi 2"
    assert result.content.title == VALID_PAYLOAD["lesson"]["title"]
    assert result.content.passage == scenario
    assert result.line_explanations[0].japanese_text == scenario
    assert all(item.example == scenario for item in result.content.items)
    assert transport.calls == ["tsuzumi-id"]


def test_explain_mode_rejects_added_or_rewritten_japanese_text() -> None:
    rewritten = json.dumps(explain_payload("仕様について確認してもよろしいでしょうか。"))
    transport = FakeTransport([rewritten] * 4)

    with pytest.raises(GenerationError, match="could not generate"):
        generator(transport).generate_lesson_content(
            "会議の日程を確認したいです。", ScenarioMode.EXPLAIN, profile()
        )


def test_generated_package_requires_complete_line_explanations() -> None:
    package = GeneratedLessonContentPackage.model_validate(content_payload())

    with pytest.raises(ValueError, match="every passage line"):
        validate_explanations(package.lesson, package.line_explanations[:-1])


def test_generated_package_rejects_english_only_quiz_targets() -> None:
    english_target = content_payload()
    english_target["lesson"]["items"][0]["expression"] = "requirement"
    english_target["line_explanations"][0]["vocabulary"][0][
        "expression"
    ] = "requirement"

    with pytest.raises(ValueError, match="Japanese language items"):
        GeneratedLessonContentPackage.model_validate(english_target)


def test_nomikai_scenario_outranks_technical_profile_in_prompt() -> None:
    transport = FakeTransport([json.dumps(conversation_payload())])

    generator(transport).generate_lesson_content(
        "Talk with my manager and colleagues at a nomikai",
        ScenarioMode.GENERATE,
        profile(),
    )

    prompt = transport.user_prompts[0]
    assert "scenario subject outranks the learner's role" in prompt
    assert "must remain social or general" in prompt
    assert "do not introduce requirements, design, coding" in prompt
    assert "required ten-line, two-speaker format" in prompt


def test_content_prompt_requires_atomic_targets_copied_from_explanations() -> None:
    prompt = lesson_prompts.content_system_prompt()

    assert "Japanese Title — English Translation" in prompt
    assert "Invent exactly two random speaker names" in prompt
    assert "japanese_speaker_name is a Japanese personal name written in kanji" in prompt
    assert "Write exactly 10 dialogue lines forming 5 exchanges" in prompt
    assert "Nameさん: Japanese dialogue" in prompt
    assert "JLPT LEVEL - STRICT REQUIREMENT" in prompt
    assert "never a sentence or utterance" in prompt
    assert "is_quiz_target to true on the 3-7 most useful points" in prompt


def test_explain_content_prompt_preserves_the_supplied_japanese_text() -> None:
    prompt = lesson_prompts.content_system_prompt(ScenarioMode.EXPLAIN)

    assert "Copy every non-empty source line" in prompt
    assert "Never add, rewrite, correct, extend, or merge Japanese sentences" in prompt
    assert "japanese_speaker_name" not in prompt


def test_dialogue_length_follows_the_learner_level() -> None:
    assert expected_line_count(profile(JapaneseLevel.N5)) == 6
    assert expected_line_count(profile(JapaneseLevel.N4)) == 8
    assert expected_line_count(profile(JapaneseLevel.N3)) == 10

    prompt = lesson_prompts.content_system_prompt(ScenarioMode.GENERATE, 6)

    assert "Write exactly 6 dialogue lines forming 3 exchanges" in prompt


def test_a_ten_line_dialogue_is_rejected_for_a_shorter_level() -> None:
    transport = FakeTransport([json.dumps(conversation_payload())] * 4)

    with pytest.raises(GenerationError):
        generator(transport).generate_lesson_content(
            "Clarify a requirement", ScenarioMode.GENERATE, profile(JapaneseLevel.N4)
        )


def test_repeated_expressions_are_explained_only_on_their_first_line() -> None:
    transport = FakeTransport([json.dumps(conversation_payload())])

    draft = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    explained = [
        (category, point.expression)
        for line in draft.line_explanations
        for category, points in (
            ("kanji", line.kanji),
            ("vocabulary", line.vocabulary),
            ("grammar", line.grammar),
        )
        for point in points
    ]

    assert len(explained) == len(set(explained))
    # The payload repeats 確認 and 〜ます on every line after the first.
    assert any(
        not (line.kanji or line.vocabulary or line.grammar)
        for line in draft.line_explanations
    )


def test_reading_questions_must_offer_kana_only_options() -> None:
    payload = quiz_payload()
    for question in payload["questions"]:
        if question["form"] == "reading":
            question["options"] = ["かくにん", "確認", "こうにん", "こうじん"]
    package = GeneratedQuizPackage.model_validate(payload)
    lesson = GeneratedLessonContentPackage.model_validate(content_payload()).lesson

    with pytest.raises(ValueError, match="kana-only options"):
        LessonGenerator._validate_quiz_contract(package, lesson)


def test_options_of_wildly_different_length_are_rejected() -> None:
    payload = quiz_payload()
    payload["questions"][0]["options"] = [
        "The written specification agreed with the whole project team",
        "Schedule",
        "Meeting",
        "Report",
    ]
    package = GeneratedQuizPackage.model_validate(payload)
    lesson = GeneratedLessonContentPackage.model_validate(content_payload()).lesson

    with pytest.raises(ValueError, match="comparable in length"):
        LessonGenerator._validate_quiz_contract(package, lesson)


def test_hedging_starts_the_fallback_while_the_primary_is_slow() -> None:
    transport = HedgeTransport(
        {
            "tsuzumi-id": (0.5, json.dumps(conversation_payload())),
            "gpt-id": (0.0, json.dumps(conversation_payload())),
        }
    )
    service = LessonGenerationService(
        transport, "tsuzumi-id", "gpt-id", hedge_after_seconds=0.05
    )

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.provider_name == "GPT-5 nano"
    assert transport.calls == ["tsuzumi-id", "gpt-id"]


def test_hedging_never_calls_the_fallback_when_the_primary_answers_first() -> None:
    transport = HedgeTransport(
        {"tsuzumi-id": (0.0, json.dumps(conversation_payload()))}
    )
    service = LessonGenerationService(
        transport, "tsuzumi-id", "gpt-id", hedge_after_seconds=5.0
    )

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.provider_name == "Tsuzumi 2"
    assert transport.calls == ["tsuzumi-id"]


def test_a_fast_primary_failure_does_not_wait_for_the_hedge_window() -> None:
    transport = HedgeTransport(
        {
            "tsuzumi-id": (0.0, TimeoutError()),
            "gpt-id": (0.0, json.dumps(conversation_payload())),
        }
    )
    service = LessonGenerationService(
        transport, "tsuzumi-id", "gpt-id", hedge_after_seconds=30.0
    )

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.provider_name == "GPT-5 nano"
    assert transport.calls == ["tsuzumi-id", "gpt-id"]


class SplitTransport:
    """Answers the dialogue call once, then the matching per-line explanation call."""

    def __init__(self, dialogue: str, explanations: dict[str, str]) -> None:
        self.dialogue = dialogue
        self.explanations = explanations
        self.system_prompts: list[str] = []
        self._lock = Lock()

    def generate(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        with self._lock:
            self.system_prompts.append(system_prompt)
        if "explain one Japanese sentence" not in system_prompt:
            return self.dialogue
        line = user_prompt.split("<japanese_line>\n", 1)[1].split("\n</japanese_line>")[0]
        return self.explanations[line]


def dialogue_payload() -> dict[str, object]:
    payload = conversation_payload()
    payload["lines"] = [{"japanese_text": text} for text in DIALOGUE_TEXTS]
    return payload


def line_explanation_payloads() -> dict[str, str]:
    payloads = {}
    for index, text in enumerate(DIALOGUE_TEXTS):
        line = generated_line(index, text)
        del line["japanese_text"]
        payloads[text] = json.dumps(line)
    return payloads


def test_parallel_explanations_build_the_same_validated_package() -> None:
    transport = SplitTransport(
        json.dumps(dialogue_payload()), line_explanation_payloads()
    )
    service = LessonGenerationService(
        transport, "tsuzumi-id", "gpt-id", parallel_explanations=True
    )

    draft = service.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert draft.content.passage == VALID_PAYLOAD["lesson"]["passage"]
    assert 3 <= len(draft.content.items) <= 7
    assert len(draft.line_explanations) == len(DIALOGUE_TEXTS)
    # One dialogue call plus one call per line.
    assert len(transport.system_prompts) == len(DIALOGUE_TEXTS) + 1
    assert any(
        "Do not explain any language" in prompt for prompt in transport.system_prompts
    )


def test_the_split_path_is_off_unless_enabled() -> None:
    transport = FakeTransport([json.dumps(conversation_payload())])

    draft = generator(transport).generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )

    assert transport.calls == ["tsuzumi-id"]
    assert len(draft.line_explanations) == len(DIALOGUE_TEXTS)


def test_user_prompt_makes_jlpt_level_strict_without_stretch_content() -> None:
    prompt = lesson_prompts.user_prompt(
        ScenarioInput(scenario="Nomikai small talk", mode=ScenarioMode.GENERATE),
        profile(JapaneseLevel.N4),
        (),
        (),
    )

    assert "specified JLPT level is the primary and strict difficulty constraint" in prompt
    assert "Do not intentionally introduce higher-level language or stretch content" in prompt
    assert '"level": "JLPT N4"' in prompt


@pytest.mark.parametrize(
    ("change", "message"),
    (
        (lambda payload: payload["lesson"].update(title="English only"), "Japanese Title"),
        (
            lambda payload: payload["line_explanations"].pop(),
            "exactly 10 dialogue lines",
        ),
        (
            lambda payload: [
                line.update(
                    japanese_text=line["japanese_text"].replace(
                        "アレックスさん", "佐藤さん"
                    )
                )
                for line in payload["line_explanations"]
            ],
            "one Japanese name and one non-Japanese",
        ),
    ),
)
def test_generated_content_rejects_wrong_title_speakers_or_exchange_count(
    change, message: str
) -> None:
    payload = content_payload()
    change(payload)
    package = GeneratedLessonContentPackage.model_validate(payload)
    scenario_input = ScenarioInput(
        scenario="Clarify a requirement", mode=ScenarioMode.GENERATE
    )
    package = LessonGenerator._normalized_content_package(
        package, scenario_input
    )

    with pytest.raises(ValueError, match=message):
        LessonGenerator._validate_content_mode(package, scenario_input)


def test_blank_scenario_requests_variety_and_uses_learning_history() -> None:
    transport = FakeTransport([json.dumps(conversation_payload())])
    learned_item = ProgressRecord(
        item_id="vocabulary:kakunin",
        category=ItemCategory.VOCABULARY,
        exposure_count=3,
        correct_count=2,
        incorrect_count=1,
        mastery_score=0.65,
        dimension_scores={"recognition": 0.8},
        consecutive_successful_reviews=1,
        sm2_interval_days=3,
        sm2_ease=2.5,
        last_outcome=None,
        last_answered_at=None,
        next_review_at=None,
    )

    generator(transport).generate_lesson_content(
        "",
        ScenarioMode.GENERATE,
        profile(),
        learning_history=(learned_item,),
        recent_topic_ids=("nomikai-small-talk-01",),
    )

    prompt = transport.user_prompts[0]
    assert "varied surprise workplace lesson" in prompt
    assert "Do not default to technical content" in prompt
    assert '"item_id": "vocabulary:kakunin"' in prompt
    assert '"nomikai-small-talk-01"' in prompt


def test_total_failure_changes_no_progress(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'lesson.db').as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    from japanese_workplace_tutor.models import Base

    Base.metadata.create_all(engine)
    user = AuthenticationService(engine).register(
        "Alice", "correct horse battery staple"
    )
    lessons = LessonService(engine)
    transport = FakeTransport(["bad", "still bad", RuntimeError("provider down")])

    with pytest.raises(GenerationError, match="could not generate"):
        generator(transport).generate_lesson_content(
            "Keep this scenario", ScenarioMode.GENERATE, profile()
        )

    assert lessons.get_progress(user.id) == ()
    engine.dispose()


def test_split_generated_lesson_uses_existing_scoring_without_duplicate_exposure(
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'lesson.db').as_posix()}", _env_file=None
    )
    engine = create_database_engine(settings)
    from japanese_workplace_tutor.models import Base

    Base.metadata.create_all(engine)
    user = AuthenticationService(engine).register(
        "Alice", "correct horse battery staple"
    )
    lessons = LessonService(engine)
    generation = generator(
        FakeTransport(
            [json.dumps(conversation_payload()), json.dumps(conversation_quiz_payload())]
        )
    )
    generated_draft = generation.generate_lesson_content(
        "Clarify a requirement", ScenarioMode.GENERATE, profile()
    )
    active_draft = lessons.start_generated_lesson_draft(user.id, generated_draft)
    assert all(record.exposure_count == 1 for record in lessons.get_progress(user.id))

    generated_quiz = generation.generate_quiz(generated_draft.content)
    active = lessons.activate_generated_quiz(active_draft, generated_quiz)
    assert all(record.exposure_count == 1 for record in lessons.get_progress(user.id))

    for question in active.lesson.questions:
        result = lessons.submit_answer(
            user.id,
            active.lesson_session_id,
            question.question_id,
            question.correct_option_index,
            active_lesson=active,
        )
        assert result.is_correct

    completion = lessons.complete_lesson(user.id, active)
    assert completion.topic_id == VALID_PAYLOAD["lesson"]["topic_id"]
    assert len(lessons.get_progress(user.id)) == 3
    assert generated_draft.provider_name == "Tsuzumi 2"
    assert generated_quiz.provider_name == "Tsuzumi 2"
    engine.dispose()

    with sqlite3.connect(tmp_path / "lesson.db") as connection:
        database_dump = "\n".join(connection.iterdump())

    prohibited_content = [
        VALID_PAYLOAD["lesson"]["passage"],
        VALID_PAYLOAD["lesson"]["recap"],
    ]
    for item in VALID_PAYLOAD["lesson"]["items"]:
        prohibited_content.append(item["example"])
    for question in [
        *VALID_PAYLOAD["lesson"]["questions"],
        *VALID_PAYLOAD["retry_questions"],
    ]:
        prohibited_content.extend(
            [question["prompt"], question["explanation"], *question["options"]]
        )
    assert [value for value in prohibited_content if value in database_dump] == []