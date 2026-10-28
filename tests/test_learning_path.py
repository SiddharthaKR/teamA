"""The next situation is chosen from completed route evidence, not model prose."""

from japanese_workplace_tutor.core.learning_path import (
    SituationStep, build_today_plan,
)


STEPS = (
    SituationStep("get-by:greeting", "get-by", "Greet a coworker", "Greet a new coworker"),
    SituationStep("get-by:help", "get-by", "Ask for help", "Ask a coworker for help"),
    SituationStep("take-part:meeting", "take-part", "Join a meeting", "Prepare for a meeting"),
)


def test_new_learner_gets_first_step_for_chosen_milestone() -> None:
    plan = build_today_plan("get-by", STEPS, (), due_count=0)

    assert plan.next_step == STEPS[0]
    assert plan.completed_steps == 0
    assert plan.total_steps == 2
    assert "first" in plan.reason.lower()


def test_completed_route_advances_once_and_stays_in_milestone() -> None:
    plan = build_today_plan("get-by", STEPS,
                            ("path:get-by:greeting", "path:get-by:greeting"), due_count=0)

    assert plan.next_step == STEPS[1]
    assert plan.completed_steps == 1


def test_due_reviews_are_capped_and_can_be_skipped() -> None:
    plan = build_today_plan("take-part", STEPS, (), due_count=8)

    assert plan.review_count == 5
    assert plan.next_step == STEPS[2]


def test_exhausted_situation_route_offers_free_practice() -> None:
    plan = build_today_plan("get-by", STEPS,
                            ("path:get-by:greeting", "path:get-by:help"), due_count=0)

    assert plan.next_step is None
    assert plan.completed_steps == plan.total_steps == 2
    assert "free practice" in plan.reason.lower()
