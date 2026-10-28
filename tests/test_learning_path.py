"""The next situation is chosen from completed route evidence, not model prose."""

from japanese_workplace_tutor.core.learning_path import (
    SituationStep, build_today_plan, grade_order, route_scenario_matches,
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


def test_word_grammar_and_order_steps_advance_by_completion_metadata() -> None:
    route = (
        SituationStep("get-by:words", "get-by", "Office words", "Practice office words",
                      track="words", words=("会議", "報告")),
        SituationStep("get-by:grammar", "get-by", "Polite request", "Practice a polite request",
                      track="grammar", grammar="〜てください"),
        SituationStep("get-by:order", "get-by", "Build a phrase", "",
                      track="sentence-order", chunks=("お", "疲れ様", "です"),
                      answer="お疲れ様です"),
    )
    assert build_today_plan("get-by", route, (), due_count=0).next_step.track == "words"
    grammar_plan = build_today_plan("get-by", route, ("path:get-by:words",),
                                    due_count=0)
    assert grammar_plan.next_step.track == "grammar"
    assert "grammar" in grammar_plan.reason.lower()
    assert build_today_plan("get-by", route, (), due_count=0).local_alternative == route[1]
    assert grammar_plan.local_alternative == route[1]
    assert build_today_plan("get-by", route, ("path:get-by:grammar",),
                            due_count=0).local_alternative == route[2]
    assert build_today_plan("get-by", route, ("path:get-by:words", "path:get-by:grammar"),
                            due_count=0).next_step.track == "sentence-order"


def test_order_grading_requires_a_unique_chunk_permutation() -> None:
    chunks = ("お", "疲れ様", "です")
    assert grade_order(chunks, (0, 1, 2), "お疲れ様です") is True
    assert grade_order(chunks, (1, 0, 2), "お疲れ様です") is False
    assert grade_order(chunks, (0, 0, 2), "お疲れ様です") is None
    assert grade_order(("あ", "あ", "です"), (0, 1, 2), "ああです") is None


def test_word_route_does_not_force_words_after_learner_edits_the_scenario() -> None:
    step = SituationStep("get-by:words", "get-by", "Office words", "Office request",
                         track="words", words=("会議",))
    assert route_scenario_matches(step, "Office request", "Office request")
    assert not route_scenario_matches(step, "Office request", "My weekend party")
