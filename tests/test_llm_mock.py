"""Phase 0: offline MockLLM transport, recording transport, fixtures and golden set."""

import json
from pathlib import Path
import sys

import pytest

from japanese_workplace_tutor.generation import (
    GenerationError,
    GeneratedConversationResponse,
    LessonGenerationService,
    ScenarioMode,
    expected_line_count,
)
from japanese_workplace_tutor.llm.mock import (
    MockFixtureMissing,
    MockTransport,
    RecordingTransport,
    load_fixture_titles,
)
from japanese_workplace_tutor.profile import JapaneseLevel
from japanese_workplace_tutor.settings import Settings

from test_generation import profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "llm"
GOLDEN = ROOT / "evals" / "golden" / "v0.json"


def mock_service(fixture_dir: Path = FIXTURES) -> LessonGenerationService:
    return LessonGenerationService(MockTransport(fixture_dir), "mock-primary", "mock-fallback")


@pytest.mark.parametrize("level", list(JapaneseLevel))
def test_offline_learning_loop_passes_real_validators_for_every_level(level) -> None:
    learner = profile(level)
    service = mock_service()

    draft = service.generate_lesson_content("", ScenarioMode.GENERATE, learner)
    quiz = service.generate_quiz(draft.content)

    lines = [row for row in draft.content.passage.splitlines() if row.strip()]
    assert len(lines) == expected_line_count(learner)
    assert 3 <= len(draft.content.items) <= 7
    assert 4 <= len(quiz.questions) <= 6
    assert draft.provider_name == "Mock (offline fixtures)"


def test_offline_roleplay_challenge_and_judge() -> None:
    service = mock_service()
    draft = service.generate_lesson_content("", ScenarioMode.GENERATE, profile())

    challenge = service.generate_situation_challenge(draft.content, profile())
    judgement = service.judge_roleplay(challenge.challenge, "はい、大丈夫です。", "はい、準備しておきます。")

    assert len(challenge.challenge.opening_options) == 3
    assert judgement.verdict.goal_achieved is True


def test_missing_fixture_fails_safely_through_the_normal_error_path() -> None:
    service = mock_service()

    with pytest.raises(GenerationError):
        service.generate_lesson_content(
            "お疲れさまです。明日の会議は十時からです。", ScenarioMode.EXPLAIN, profile()
        )


def test_mock_transport_matches_first_entry_and_reports_misses(tmp_path: Path) -> None:
    (tmp_path / "Thing.json").write_text(
        json.dumps([
            {"match": ["alpha"], "response": {"value": 1}},
            {"match": [], "response": {"value": 2}},
        ]),
        encoding="utf-8",
    )
    transport = MockTransport(tmp_path)

    assert json.loads(transport.generate("m", "sys alpha", "user", {"title": "Thing"})) == {"value": 1}
    assert json.loads(transport.generate("m", "sys", "user", {"title": "Thing"})) == {"value": 2}
    with pytest.raises(MockFixtureMissing):
        transport.generate("m", "sys", "user", {"title": "Other"})
    assert [call.matched for call in transport.calls] == [True, True, False]


def test_recording_transport_appends_jsonl(tmp_path: Path) -> None:
    class Inner:
        def generate(self, model_id, system_prompt, user_prompt, response_schema=None, timeout_seconds=None):
            return '{"ok": true}'

    path = tmp_path / "rec" / "recordings.jsonl"
    transport = RecordingTransport(Inner(), path)

    assert transport.generate("gpt-x", "sys", "user", {"title": "Thing"}) == '{"ok": true}'
    transport.generate("gpt-x", "sys", "user2", {"title": "Thing"})
    rows = [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines()]
    assert [row["schema_title"] for row in rows] == ["Thing", "Thing"]
    assert rows[0]["prompt_sha256"] != rows[1]["prompt_sha256"]


def test_mock_mode_needs_no_credentials(monkeypatch) -> None:
    for name in ("JLT_MODEL_BASE_URL", "JLT_MODEL_API_KEY", "JLT_PRIMARY_MODEL", "JLT_FALLBACK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JLT_LLM_MODE", "mock")

    settings = Settings(_env_file=None)

    assert settings.model_configured is False
    assert settings.generation_available is True


def test_live_mode_is_the_default(monkeypatch) -> None:
    monkeypatch.delenv("JLT_LLM_MODE", raising=False)
    assert Settings(_env_file=None).llm_mode == "live"


def test_committed_fixtures_match_the_builder() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_mock_fixtures
    finally:
        sys.path.pop(0)

    expected = build_mock_fixtures.fixtures()
    assert set(load_fixture_titles(FIXTURES)) == set(expected)
    for title, entries in expected.items():
        committed = json.loads((FIXTURES / f"{title}.json").read_text(encoding="utf-8"))
        assert committed == json.loads(json.dumps(entries, ensure_ascii=False)), title


def test_conversation_fixture_covers_each_line_count() -> None:
    entries = json.loads((FIXTURES / "GeneratedConversationResponse.json").read_text(encoding="utf-8"))
    counts = sorted(len(GeneratedConversationResponse.model_validate(e["response"]).lines) for e in entries)
    assert counts == [6, 8, 10]


def test_golden_set_v0_is_well_formed() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    cases = golden["cases"]
    ids = [case["id"] for case in cases]

    assert golden["version"] == "v0"
    assert len(cases) >= 50
    assert len(ids) == len(set(ids))
    assert {case["feature"] for case in cases} == {"lesson", "deck_localizer"}
    levels = {case["profile"]["level"] for case in cases if case["feature"] == "lesson"}
    assert levels == {level.value for level in JapaneseLevel}
    assert all(case["checks"] for case in cases)
    assert all(case.get("public_content", True) for case in cases)
