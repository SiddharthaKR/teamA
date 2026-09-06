"""Tests for the situation-roleplay stage: challenge schema, deterministic
graduation, and per-phase routing (challenge to the Japanese model, judge to
the structured model). Reuses fixtures from ``test_generation``.
"""

import pytest

from japanese_workplace_tutor.generation import (
    Comprehensibility,
    LessonGenerationService,
    Recovery,
    RoleplayVerdict,
    SituationChallenge,
    evaluate_graduation,
)
from japanese_workplace_tutor.lesson import FixtureItem, LessonContent

from test_generation import FakeTransport, profile


def _challenge_kwargs() -> dict:
    return dict(
        goal="Confirm a spec requirement and get agreement",
        setting="Desk-side before a meeting",
        learner_role="engineer",
        counterpart_role="your manager",
        success_criteria=("goal reached", "comprehensible", "polite register"),
        toolkit=[
            {"japanese": "仕様", "reading": "しよう", "meaning": "specification", "kind": "target"},
            {"japanese": "もう一度お願いします", "reading": "もういちどおねがいします", "meaning": "please repeat", "kind": "recovery"},
        ],
        opening_line="仕様について確認したいのですが。",
        opening_options=("はい、確認させてください。", "え、なんで？", "別の話をしましょう。"),
        curveball_type="follow-up question",
        curveball_line="いつまでに必要ですか。",
        curveball_options=("明日までに確認します。", "知りません。", "たぶん。"),
    )


def _verdict(**overrides) -> RoleplayVerdict:
    base = dict(
        goal_achieved=True,
        goal_evidence="got agreement",
        comprehensible=Comprehensibility.MOSTLY,
        comprehensible_evidence="clear",
        register_appropriate=True,
        register_evidence="polite",
        recovered_from_curveball=Recovery.PARTLY,
        recovery_evidence="answered the timing question",
    )
    base.update(overrides)
    return RoleplayVerdict(**base)


def _content() -> LessonContent:
    return LessonContent(
        topic_id="t1",
        title="確認 — Confirm",
        difficulty="JLPT N4",
        passage="山田さん: 確認してもよろしいでしょうか。",
        items=(
            FixtureItem(canonical_id="v:1", category="vocabulary", expression="仕様", reading="しよう", meaning="spec", example="仕様を確認します。", jlpt_level="JLPT N3", jlpt_provenance="model-estimate", jlpt_confidence=0.7),
            FixtureItem(canonical_id="v:2", category="vocabulary", expression="確認", reading="かくにん", meaning="confirm", example="日程を確認します。", jlpt_level="JLPT N4", jlpt_provenance="model-estimate", jlpt_confidence=0.8),
            FixtureItem(canonical_id="g:1", category="grammar", expression="〜てもよろしいでしょうか", reading="てもよろしいでしょうか", meaning="May I", example="質問してもよろしいでしょうか。", jlpt_level="JLPT N3", jlpt_provenance="model-estimate", jlpt_confidence=0.7),
        ),
        recap="Use politely.",
    )


def test_challenge_schema_validates() -> None:
    challenge = SituationChallenge(**_challenge_kwargs())
    assert len(challenge.success_criteria) == 3
    assert any(phrase.kind == "recovery" for phrase in challenge.toolkit)


def test_challenge_rejects_duplicate_options() -> None:
    kwargs = _challenge_kwargs()
    kwargs["opening_options"] = ("同じ", "同じ", "別の話をしましょう。")
    with pytest.raises(ValueError, match="distinct"):
        SituationChallenge(**kwargs)


@pytest.mark.parametrize(
    ("overrides", "graduated", "failed"),
    (
        ({}, True, ()),
        ({"goal_achieved": False}, False, ("goal",)),
        ({"comprehensible": Comprehensibility.NO}, False, ("comprehensibility",)),
        ({"register_appropriate": False}, False, ("register",)),
        ({"recovered_from_curveball": Recovery.NO}, False, ("recovery",)),
        ({"comprehensible": Comprehensibility.YES}, True, ()),
        ({"recovered_from_curveball": Recovery.YES}, True, ()),
    ),
)
def test_graduation_is_deterministic(overrides, graduated, failed) -> None:
    result = evaluate_graduation(_verdict(**overrides))
    assert result.graduated is graduated
    assert result.failed_criteria == failed


def test_challenge_uses_primary_and_judge_routes_to_quiz_model() -> None:
    challenge = SituationChallenge(**_challenge_kwargs())
    verdict = _verdict()
    transport = FakeTransport([challenge.model_dump_json(), verdict.model_dump_json()])
    service = LessonGenerationService(
        transport,
        "tsuzumi2",
        "gpt-5-nano",
        quiz_primary_model="gpt-5-nano",
        quiz_fallback_model="tsuzumi2",
    )

    generated = service.generate_situation_challenge(_content(), profile())
    # The challenge is Japanese generation, so it uses the global primary.
    assert generated.provider_name == "Tsuzumi 2"

    judgement = service.judge_roleplay(
        generated.challenge, "はい、確認させてください。", "明日までに確認します。"
    )
    # The judge is a strict-JSON step, so it routes to the structured model.
    assert judgement.provider_name == "GPT-5 nano"
    assert transport.calls == ["tsuzumi2", "gpt-5-nano"]
    assert judgement.verdict.goal_achieved is True
