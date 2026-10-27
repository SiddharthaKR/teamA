from japanese_workplace_tutor.core.priority import Candidate, rank_targets


def item(name: str, *, domain: float = 0.0, mastery: float = 0.0,
         importance: str = "A", due: bool = False, eligible: bool = True) -> Candidate:
    return Candidate(name, name, domain, 0.0, 0.0, 0.5, importance, mastery, eligible, due)


def test_domain_and_personal_importance_change_the_target_order() -> None:
    ranked = rank_targets((
        item("general"),
        item("software", domain=1.0),
        item("personal", importance="S", domain=0.8),
    ))
    assert [row.item_id for row in ranked] == ["personal", "software", "general"]
    assert ranked[0].reason == "personal priority"


def test_due_word_can_reappear_even_at_full_mastery() -> None:
    ranked = rank_targets((
        item("new", domain=1.0),
        item("due", mastery=1.0, due=True),
    ))
    assert [row.item_id for row in ranked] == ["due", "new"]
    assert ranked[0].reason == "due for review"


def test_level_filter_and_ties_are_deterministic() -> None:
    ranked = rank_targets((item("z"), item("a"), item("excluded", eligible=False)))
    assert [row.item_id for row in ranked] == ["a", "z"]


def test_duplicate_candidates_are_selected_once() -> None:
    ranked = rank_targets((item("due", due=True), item("due", due=True), item("new")))
    assert [row.item_id for row in ranked] == ["due", "new"]
