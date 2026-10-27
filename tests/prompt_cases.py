"""Shared prompt-snapshot inputs.

The snapshot file tests/snapshots/prompts_v1.json was captured from the
hackathon build (tag hackathon-final) with these exact inputs. Refactors must
reproduce every prompt byte for byte; a deliberate prompt change bumps the
feature's PROMPT_VERSION and re-captures the snapshot.
"""

from datetime import datetime
import json
from pathlib import Path

from japanese_workplace_tutor.generation import (
    ScenarioInput,
    ScenarioMode,
    SituationChallenge,
    SlideDeliveryCoaching,
    SlideInput,
)
from japanese_workplace_tutor.lesson import (
    FixtureItem,
    ItemCategory,
    LessonContent,
    ProgressRecord,
    ReviewOutcome,
)
from japanese_workplace_tutor.profile import JapaneseLevel, LevelSource, ProfileRecord

SNAPSHOT_PATH = Path(__file__).resolve().parent / "snapshots" / "prompts_v1.json"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"


def _profile(level: JapaneseLevel, role: str = "Software engineer", domain: str | None = None) -> ProfileRecord:
    return ProfileRecord(
        user_id=1,
        role=role,
        tasks=("Discuss requirements", "Report progress"),
        tools_domain=domain,
        declared_level=level,
        estimated_working_level=None,
        level_source=LevelSource.SELF_REPORTED,
        level_confidence=1.0,
        romaji_preference=False,
    )


HISTORY = (
    ProgressRecord(
        item_id="kanji:abc", category=ItemCategory.KANJI, exposure_count=3, correct_count=1,
        incorrect_count=2, mastery_score=0.1, dimension_scores={"reading": 0.0},
        consecutive_successful_reviews=0, sm2_interval_days=0, sm2_ease=2.3,
        last_outcome=ReviewOutcome.AGAIN, last_answered_at=datetime(2026, 10, 1, 9, 0),
        next_review_at=datetime(2026, 10, 1, 9, 10),
    ),
    ProgressRecord(
        item_id="grammar:def", category=ItemCategory.GRAMMAR, exposure_count=5, correct_count=4,
        incorrect_count=0, mastery_score=0.74, dimension_scores={"grammar_application": 0.6},
        consecutive_successful_reviews=2, sm2_interval_days=7, sm2_ease=2.4,
        last_outcome=ReviewOutcome.GOOD, last_answered_at=datetime(2026, 10, 2, 9, 0),
        next_review_at=datetime(2026, 10, 9, 9, 0),
    ),
)

CONTENT = LessonContent(
    topic_id="meeting-reschedule",
    title="会議の時間の変更 — Changing a Meeting Time",
    difficulty="JLPT N4",
    passage="田中さん: 明日の会議の時間を変えてもいいですか。\nリンさん: はい、大丈夫です。",
    items=(
        FixtureItem(canonical_id="kanji:1", category="kanji", expression="会議", reading="かいぎ", meaning="meeting", example="明日の会議の時間を変えてもいいですか。", jlpt_level="JLPT N4", jlpt_provenance="model-estimate", jlpt_confidence=0.6),
        FixtureItem(canonical_id="grammar:1", category="grammar", expression="〜てもいいですか", reading="てもいいですか", meaning="May I", example="明日の会議の時間を変えてもいいですか。", jlpt_level="JLPT N5", jlpt_provenance="model-estimate", jlpt_confidence=0.6),
        FixtureItem(canonical_id="vocabulary:1", category="vocabulary", expression="大丈夫", reading="だいじょうぶ", meaning="all right", example="はい、大丈夫です。", jlpt_level="JLPT N4", jlpt_provenance="model-estimate", jlpt_confidence=0.6),
    ),
    recap="Asked permission to change a time.",
)

SLIDES = (
    SlideInput(title="Weekly status", body="Done: API tests passed\nRisk: vendor delay"),
    SlideInput(title="Next steps", body="Integration test on Nov 5"),
)

CONTEXTS = {
    "default": {},
    "status": {"audience": "your manager", "formality": "polite", "purpose": "a weekly update", "deck_type": "status"},
    "technical": {"audience": "engineers", "deck_type": "technical"},
    "business": {"audience": "a client executive", "formality": "very formal", "deck_type": "business"},
    "casual_di": {"deck_type": "casual_di"},
    "speech": {"purpose": "an all-hands speech", "deck_type": "speech"},
    "unknown": {"deck_type": "not-a-type"},
}


def _challenge() -> SituationChallenge:
    entries = json.loads((FIXTURES / "SituationChallenge.json").read_text(encoding="utf-8"))
    return SituationChallenge.model_validate(entries[0]["response"])


COACHING = SlideDeliveryCoaching(
    key_message="Status is on track",
    spoken_script="今週の進捗をご報告します。",
    transition_in="続きまして、進捗についてご説明します。",
    delivery_tips="Pause after the status.",
    rehearsal_options=("進捗は順調です。", "まあまあです。", "来期の話をします。"),
)

LEVELS = list(JapaneseLevel)
SCENARIOS = {
    "surprise": ScenarioInput(scenario="", mode=ScenarioMode.GENERATE),
    "english": ScenarioInput(scenario="Ask my manager to move tomorrow's meeting", mode=ScenarioMode.GENERATE),
    "japanese": ScenarioInput(scenario="明日の会議は十時からです。\n資料を確認してください。", mode=ScenarioMode.EXPLAIN),
}


def cases() -> list[tuple[str, str, tuple]]:
    """Return (case_id, prompt_name, args) for every prompt builder."""

    out: list[tuple[str, str, tuple]] = []
    for mode in ScenarioMode:
        for count in (6, 8, 10):
            out.append((f"dialogue_system/{mode.name}/{count}", "dialogue_system", (mode, count)))
            out.append((f"content_system/{mode.name}/{count}", "content_system", (mode, count)))
    for level in LEVELS:
        out.append((f"line_explanation_system/{level.name}", "line_explanation_system", (level,)))
    out.append(("line_explanation_user", "line_explanation_user", ("明日の会議の時間を変えてもいいですか。",)))
    out.append(("quiz_system", "quiz_system", ()))
    for name, scenario in SCENARIOS.items():
        for level in LEVELS:
            for history_name, history in (("empty", ()), ("history", HISTORY)):
                out.append((
                    f"user/{name}/{level.name}/{history_name}", "user",
                    (scenario, _profile(level, domain="IOWN"), history, ("topic-a", "topic-b")),
                ))
    out.append(("quiz_user/empty", "quiz_user", (CONTENT, ())))
    out.append(("quiz_user/history", "quiz_user", (CONTENT, HISTORY)))
    for level in LEVELS:
        out.append((f"challenge_system/{level.name}", "challenge_system", (_profile(level, role="Sales"),)))
    out.append(("challenge_user", "challenge_user", (CONTENT,)))
    out.append(("judge_system", "judge_system", ()))
    out.append(("judge_user", "judge_user", (_challenge(), "はい、大丈夫です。", "はい、準備しておきます。")))
    for name, context in CONTEXTS.items():
        out.append((f"presentation_context/{name}", "presentation_context", (context,)))
        out.append((f"slide_localize_system/{name}", "slide_localize_system", (context,)))
        out.append((f"deck_flow_system/{name}", "deck_flow_system", (context,)))
        out.append((f"delivery_coach_system/{name}", "delivery_coach_system", (context,)))
        out.append((f"delivery_judge_system/{name}", "delivery_judge_system", (context,)))
    out.append(("slide_localize_user", "slide_localize_user", (SLIDES[0],)))
    out.append(("deck_flow_user", "deck_flow_user", (SLIDES,)))
    out.append(("delivery_coach_user", "delivery_coach_user", (SLIDES[1], 2, 2)))
    out.append(("delivery_judge_user", "delivery_judge_user", (COACHING, SLIDES[0], "進捗は順調です。")))
    out.append(("repair", "repair", ("original prompt", "Fix these validation errors: x")))
    return out


def render(builders: dict) -> dict[str, str]:
    return {case_id: builders[name](*args) for case_id, name, args in cases()}
