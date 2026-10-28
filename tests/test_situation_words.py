from datetime import datetime
from dataclasses import replace
import pytest

from japanese_workplace_tutor.core.items import ItemCategory
from japanese_workplace_tutor.core.learner import JapaneseLevel, LevelSource, ProfileRecord
from japanese_workplace_tutor.core.progress import ProgressRecord
from japanese_workplace_tutor.features.lessons import canonical_item_id
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit
from japanese_workplace_tutor.situation_words import SituationWordService


def profile(level: JapaneseLevel = JapaneseLevel.N3) -> ProfileRecord:
    return ProfileRecord(1, "Software engineer", (), None, level, None,
                         LevelSource.SELF_REPORTED, 1.0, False)


def test_situation_set_references_resolve_and_unknown_scenario_is_unforced() -> None:
    service = SituationWordService(SudachiToolkit.shared())
    assert service.validate_references() == ()
    assert service.match("I need to give a status update to my manager") == "status-update"
    assert service.match("Talk about the weather") is None
    assert service.lesson_targets("Talk about the weather", profile(), (),
                                  datetime(2026, 11, 1)) == ()


def test_situation_words_are_level_filtered_and_rotate_by_exposure() -> None:
    toolkit = SudachiToolkit.shared()
    service = SituationWordService(toolkit)
    first = service.lesson_targets("Prepare for a meeting", profile(JapaneseLevel.N4), (),
                                   datetime(2026, 11, 1))
    assert first
    assert all(toolkit.lookup(row.expression).level in {"N5", "N4", "N3"}
               for row in first)
    used = first[0]
    progress = ProgressRecord(used.item_id, ItemCategory.VOCABULARY, 3, 0, 0,
                              0.0, {}, 0, 0, 2.5, None, None, None)
    second = service.lesson_targets("Prepare for a meeting", profile(JapaneseLevel.N4),
                                    (progress,), datetime(2026, 11, 1))
    assert second and second[0].item_id != used.item_id


def test_mastered_situation_word_waits_until_due() -> None:
    toolkit = SudachiToolkit.shared()
    service = SituationWordService(toolkit)
    item_id = canonical_item_id(ItemCategory.VOCABULARY, "会議", toolkit)
    mastered = ProgressRecord(item_id, ItemCategory.VOCABULARY, 0, 3, 0, 1.0,
                              {}, 3, 10, 2.5, None, None, None)
    targets = service.lesson_targets("meeting", profile(), (mastered,),
                                     datetime(2026, 11, 1))
    assert all(row.item_id != item_id for row in targets)
    due = replace(mastered, next_review_at=datetime(2026, 10, 31))
    assert service.lesson_targets("meeting", profile(), (due,),
                                  datetime(2026, 11, 1))[0].item_id == item_id


@pytest.mark.parametrize("scenario", [
    "A meeting about the company party",
    "Discuss weekend plans in a team meeting",
    "Give a status update on the office party",
    "Talk about a requirements document for a social event",
])
def test_mixed_social_scenarios_do_not_force_workplace_words(scenario: str) -> None:
    service = SituationWordService(SudachiToolkit.shared())

    assert service.lesson_targets(scenario, profile(), (),
                                  datetime(2026, 11, 1)) == ()


def test_handover_and_customer_followup_have_reference_backed_sets() -> None:
    service = SituationWordService(SudachiToolkit.shared())
    assert service.match("Prepare a handover for my coworker") == "handover"
    assert service.match("Follow up with a customer about a request") == "customer-followup"
    assert service.lesson_targets("Prepare a handover for my coworker",
                                  profile(), (), datetime(2026, 11, 1))
    assert service.validate_references() == ()


def test_known_work_situation_uses_partner_context_to_rank_its_words() -> None:
    service = SituationWordService(SudachiToolkit.shared())
    manager = service.lesson_targets("Give a status update to my manager",
                                     profile(), (), datetime(2026, 11, 1))
    coworker = service.lesson_targets("Give a status update to my coworker",
                                      profile(), (), datetime(2026, 11, 1))
    assert manager[0].expression == "報告"
    assert coworker[0].expression == "確認"


def test_known_requirement_situation_uses_role_domain_context() -> None:
    service = SituationWordService(SudachiToolkit.shared())
    generic = replace(profile(), role="Office worker")
    software = profile()
    scenario = "Clarify a requirement"
    generic_words = service.lesson_targets(scenario, generic, (), datetime(2026, 11, 1))
    software_words = service.lesson_targets(scenario, software, (), datetime(2026, 11, 1))
    assert {row.expression for row in generic_words} == {"仕様", "確認"}
    assert {row.expression for row in software_words} == {"仕様", "課題"}
