"""Pack targets are local, reference-backed, and never leak between users."""

from datetime import datetime

from japanese_workplace_tutor.core.items import ItemCategory
from japanese_workplace_tutor.core.learner import JapaneseLevel, LevelSource, ProfileRecord
from japanese_workplace_tutor.core.progress import ProgressRecord
from japanese_workplace_tutor.domain_words import DomainWordService
from japanese_workplace_tutor.features.lessons import canonical_item_id
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit


NOW = datetime(2026, 11, 1)


def profile(role: str, domain: str | None = None) -> ProfileRecord:
    return ProfileRecord(1, role, (), domain, JapaneseLevel.N3, None,
                         LevelSource.SELF_REPORTED, 1.0, False)


def test_pack_references_resolve_and_unknown_role_uses_general_office() -> None:
    service = DomainWordService(SudachiToolkit.shared())
    assert service.validate_references() == ()
    assert service.pack_ids_for(profile("Unlisted role")) == ("general-office",)
    assert "software" in service.pack_ids_for(profile("Software engineer"))
    assert "sales" in service.pack_ids_for(profile("Account executive", "Sales"))
    assert service.pack_ids_for(profile("Mechanical engineer")) == ("general-office",)
    assert service.pack_ids_for(profile("Marketing specialist")) == ("general-office",)


def test_blank_lesson_rotates_and_includes_due_word_outside_pack() -> None:
    service = DomainWordService(SudachiToolkit.shared())
    learner = profile("Unlisted role")
    initial = service.lesson_targets("", learner, (), NOW)
    assert initial
    first = initial[0]
    used = ProgressRecord(first.item_id, ItemCategory.VOCABULARY, 4, 0, 0,
                          0.0, {}, 0, 0, 2.5, None, None, None,
                          first.expression)
    rotated = service.lesson_targets("", learner, (used,), NOW)
    assert rotated[0].item_id != first.item_id

    outside = ProgressRecord(canonical_item_id(ItemCategory.VOCABULARY, "仕様",
                                                SudachiToolkit.shared()), ItemCategory.VOCABULARY,
                             1, 1, 0, 1.0, {}, 1, 1, 2.5, None, None,
                             datetime(2026, 10, 31), "仕様")
    due = service.lesson_targets("", learner, (outside,), NOW)
    assert due[0].expression == "仕様"
    assert due[0].reason == "due for review"


def test_unrelated_personal_scenario_does_not_force_pack_words() -> None:
    service = DomainWordService(SudachiToolkit.shared())
    assert service.lesson_targets("Talk about my weekend party", profile("Engineer"),
                                  (), NOW) == ()


def test_word_route_uses_only_its_reference_backed_words() -> None:
    service = DomainWordService(SudachiToolkit.shared())
    targets = service.route_targets(("会議", "報告"), profile("Engineer"), (), NOW)
    assert {row.expression for row in targets} == {"会議", "報告"}
    assert service.route_targets(("made-up",), profile("Engineer"), (), NOW) == ()
