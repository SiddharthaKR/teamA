from datetime import datetime
from dataclasses import replace

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
