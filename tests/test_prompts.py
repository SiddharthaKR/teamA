"""Every prompt builder reproduces the hackathon wording byte for byte.

The snapshot was captured from tag hackathon-final. If a prompt changes on
purpose, bump that feature's PROMPT_VERSION and re-capture the snapshot in the
same commit, so recorded evidence can say which wording produced it.
"""

import json

import pytest

from japanese_workplace_tutor.llm.gateway import LLMGateway
from japanese_workplace_tutor.prompts import lessons, presentation, roleplay

from prompt_cases import SNAPSHOT_PATH, cases, render

BUILDERS = {
    "dialogue_system": lessons.dialogue_system_prompt,
    "content_system": lessons.content_system_prompt,
    "line_explanation_system": lessons.line_explanation_system_prompt,
    "line_explanation_user": lessons.line_explanation_user_prompt,
    "quiz_system": lessons.quiz_system_prompt,
    "user": lessons.user_prompt,
    "quiz_user": lessons.quiz_user_prompt,
    "challenge_system": roleplay.challenge_system_prompt,
    "challenge_user": roleplay.challenge_user_prompt,
    "judge_system": roleplay.judge_system_prompt,
    "judge_user": roleplay.judge_user_prompt,
    "presentation_context": presentation.presentation_context,
    "slide_localize_system": presentation.slide_localize_system_prompt,
    "slide_localize_user": presentation.slide_localize_user_prompt,
    "deck_flow_system": presentation.deck_flow_system_prompt,
    "deck_flow_user": presentation.deck_flow_user_prompt,
    "delivery_coach_system": presentation.delivery_coach_system_prompt,
    "delivery_coach_user": presentation.delivery_coach_user_prompt,
    "delivery_judge_system": presentation.delivery_judge_system_prompt,
    "delivery_judge_user": presentation.delivery_judge_user_prompt,
    "repair": LLMGateway._repair_prompt,
}
SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
RENDERED = render(BUILDERS)


def test_snapshot_covers_every_case() -> None:
    assert set(SNAPSHOT) == {case_id for case_id, _, _ in cases()}


@pytest.mark.parametrize("case_id", sorted(SNAPSHOT))
def test_prompt_matches_snapshot(case_id: str) -> None:
    assert RENDERED[case_id] == SNAPSHOT[case_id]


def test_prompt_versions_are_declared() -> None:
    assert lessons.PROMPT_VERSION == "lessons-v2"
    assert roleplay.PROMPT_VERSION == "roleplay-v1"
    assert presentation.PROMPT_VERSION == "presentation-v1"
