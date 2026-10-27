from pathlib import Path
from datetime import datetime

import pytest

from japanese_workplace_tutor.auth import AuthenticationService
from japanese_workplace_tutor.database import create_database_engine
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit
from japanese_workplace_tutor.models import Base
from japanese_workplace_tutor.personal_terms import PersonalTermService, TermValidationError
from japanese_workplace_tutor.core.learner import JapaneseLevel, LevelSource, ProfileRecord
from japanese_workplace_tutor.settings import Settings


def services(path: Path):
    engine = create_database_engine(
        Settings(database_url=f"sqlite:///{path.as_posix()}", _env_file=None)
    )
    Base.metadata.create_all(engine)
    return AuthenticationService(engine), PersonalTermService(engine, SudachiToolkit.shared()), engine


def test_paste_preview_and_save_are_user_scoped(tmp_path: Path) -> None:
    auth, terms, engine = services(tmp_path / "terms.db")
    alice = auth.register("Alice", "correct horse battery staple")
    bob = auth.register("Bob", "another secure password")

    preview = terms.preview(alice.id, "会議, meeting\n会議, meeting\nhello", kind="word")
    assert [row.status for row in preview] == ["ready", "duplicate", "rejected"]
    assert preview[0].reading
    with pytest.raises(TermValidationError, match="public"):
        terms.save(alice.id, preview, public_confirmed=False)
    assert terms.list_terms(alice.id) == ()

    assert terms.save(alice.id, preview, public_confirmed=True) == 1
    assert len(terms.list_terms(alice.id)) == 1
    assert terms.list_terms(bob.id) == ()
    engine.dispose()


def test_unknown_grammar_is_kept_as_practice_only(tmp_path: Path) -> None:
    auth, terms, engine = services(tmp_path / "terms.db")
    user = auth.register("Alice", "correct horse battery staple")
    preview = terms.preview(user.id, "謎の文法", kind="grammar")
    assert preview[0].status == "unverified"
    terms.save(user.id, preview, public_confirmed=True)
    assert terms.list_terms(user.id)[0].reference_id is None
    engine.dispose()


def test_paste_limits_and_importance(tmp_path: Path) -> None:
    auth, terms, engine = services(tmp_path / "terms.db")
    user = auth.register("Alice", "correct horse battery staple")
    with pytest.raises(TermValidationError, match="500"):
        terms.preview(user.id, "会議\n" * 501, kind="word")
    preview = terms.preview(user.id, "S 会議, meeting", kind="word", importance="B")
    assert preview[0].importance == "S"
    engine.dispose()


def test_priority_and_hiding_do_not_cross_users(tmp_path: Path) -> None:
    auth, terms, engine = services(tmp_path / "terms.db")
    alice = auth.register("Alice", "correct horse battery staple")
    bob = auth.register("Bob", "another secure password")
    terms.save(alice.id, terms.preview(alice.id, "会議", kind="word"), public_confirmed=True)
    term = terms.list_terms(alice.id)[0]
    assert terms.set_importance(bob.id, term.id, "S") is False
    assert terms.set_importance(alice.id, term.id, "S") is True
    assert terms.set_hidden(alice.id, term.id, True) is True
    assert terms.list_terms(alice.id)[0].importance == "S"
    assert terms.list_terms(alice.id)[0].status == "hidden"
    engine.dispose()


def test_stale_preview_does_not_insert_duplicates(tmp_path: Path) -> None:
    auth, terms, engine = services(tmp_path / "terms.db")
    user = auth.register("Alice", "correct horse battery staple")
    preview = terms.preview(user.id, "会議", kind="word")
    assert terms.save(user.id, preview, public_confirmed=True) == 1
    assert terms.save(user.id, preview, public_confirmed=True) == 0
    assert len(terms.list_terms(user.id)) == 1
    engine.dispose()


def test_verified_personal_words_become_ranked_lesson_targets(tmp_path: Path) -> None:
    auth, terms, engine = services(tmp_path / "terms.db")
    user = auth.register("Alice", "correct horse battery staple")
    terms.save(user.id, terms.preview(user.id, "S 仕様\nB 確認\n謎の語", kind="word"), public_confirmed=True)
    profile = ProfileRecord(user.id, "Software engineer", (), None, JapaneseLevel.N3,
                            None, LevelSource.SELF_REPORTED, 1.0, False)

    ranked = terms.lesson_targets(user.id, profile, (), datetime(2026, 11, 1))

    assert [row.expression for row in ranked] == ["仕様", "確認"]
    terms.set_hidden(user.id, terms.list_terms(user.id)[0].id, True)
    assert [row.expression for row in terms.lesson_targets(user.id, profile, (),
                                                            datetime(2026, 11, 1))] == ["確認"]
    engine.dispose()
