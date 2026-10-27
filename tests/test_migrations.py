from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config

from japanese_workplace_tutor.settings import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def configure_database(monkeypatch, database_path: Path) -> Config:
    monkeypatch.setenv("JLT_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def assert_t05_schema(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        user_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        profile_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(learner_profiles)"
            ).fetchall()
        }
        profile_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(learner_profiles)"
        ).fetchall()
        progress_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(user_item_progress)"
            ).fetchall()
        }
        attempt_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(review_attempts)").fetchall()
        }
        completion_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(completed_lesson_metadata)"
            ).fetchall()
        }
        learning_item_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(learning_items)").fetchall()
        }
        progress_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(user_item_progress)"
        ).fetchall()
        attempt_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(review_attempts)"
        ).fetchall()
        completion_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(completed_lesson_metadata)"
        ).fetchall()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert revision == ("20261028_0012",)
    assert user_columns == {
        "id",
        "username",
        "normalized_username",
        "password_hash",
        "created_at",
        "updated_at",
    }
    assert profile_columns == {
        "id",
        "user_id",
        "role",
        "tasks",
        "tools_domain",
        "declared_level",
        "estimated_working_level",
        "level_source",
        "level_confidence",
        "romaji_preference",
        "milestone_id",
        "created_at",
        "updated_at",
    }
    assert len(profile_foreign_keys) == 1
    assert profile_foreign_keys[0][2:5] == ("users", "user_id", "id")
    assert profile_foreign_keys[0][6] == "CASCADE"
    assert learning_item_columns == {
        "canonical_id",
        "category",
        "expression",
        "jlpt_level",
        "jlpt_provenance",
        "jlpt_confidence",
        "created_at",
    }
    assert progress_columns == {
        "id",
        "user_id",
        "item_id",
        "exposure_count",
        "correct_count",
        "incorrect_count",
        "mastery_score",
        "dimension_scores",
        "consecutive_successful_reviews",
        "sm2_interval_days",
        "sm2_ease",
        "last_outcome",
        "last_answered_at",
        "next_review_at",
        "policy_version",
        "created_at",
        "updated_at",
    }
    assert attempt_columns == {
        "id",
        "user_id",
        "item_id",
        "lesson_session_id",
        "idempotency_key",
        "question_form",
        "skill_dimension",
        "answer_confidence",
        "is_correct",
        "is_retry",
        "is_graded",
        "outcome",
        "policy_version",
        "answered_at",
    }
    assert completion_columns == {
        "id",
        "user_id",
        "lesson_session_id",
        "topic_id",
        "difficulty",
        "studied_item_ids",
        "completed_at",
    }
    assert {(row[2], row[3], row[4], row[6]) for row in progress_foreign_keys} == {
        ("users", "user_id", "id", "CASCADE"),
        ("learning_items", "item_id", "canonical_id", "RESTRICT"),
    }
    assert {(row[2], row[3], row[4], row[6]) for row in attempt_foreign_keys} == {
        ("users", "user_id", "id", "CASCADE"),
        ("learning_items", "item_id", "canonical_id", "RESTRICT"),
    }
    assert {(row[2], row[3], row[4], row[6]) for row in completion_foreign_keys} == {
        ("users", "user_id", "id", "CASCADE"),
    }
    assert violations == []
    with sqlite3.connect(database_path) as connection:
        assert {row[1] for row in connection.execute("PRAGMA table_info(personal_terms)")} == {
            "id", "user_id", "kind", "expression", "reference_id", "reading",
            "meaning", "importance", "status", "source", "created_at",
        }
        assert connection.execute("PRAGMA foreign_key_list(personal_terms)").fetchone()[6] == "CASCADE"


def test_clean_database_upgrades_to_t05_head(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = configure_database(monkeypatch, database_path)

    command.upgrade(config, "head")

    assert_t05_schema(database_path)
    get_settings.cache_clear()


def test_t04_database_upgrades_to_t05_head(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = configure_database(monkeypatch, database_path)

    command.upgrade(config, "20260831_0004")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users (username, normalized_username, password_hash) "
            "VALUES ('Alice', 'alice', 'test-hash')"
        )
        connection.execute(
            "INSERT INTO learner_profiles (user_id, role, tasks, declared_level) "
            "VALUES (1, 'Researcher', '[]', 'JLPT N4')"
        )
        connection.execute(
            "INSERT INTO learning_items "
            "(canonical_id, category, jlpt_level, jlpt_provenance, jlpt_confidence) "
            "VALUES ('grammar:test', 'grammar', 'JLPT N4', 'fixture-reference', 0.9)"
        )
        connection.execute(
            "INSERT INTO user_item_progress "
            "(user_id, item_id, correct_count, incorrect_count, mastery_score) "
            "VALUES (1, 'grammar:test', 0, 1, 0.1)"
        )
        connection.execute(
            "INSERT INTO review_attempts "
            "(user_id, item_id, lesson_session_id, idempotency_key, question_form, "
            "is_correct, is_retry, answered_at) VALUES "
            "(1, 'grammar:test', '11111111-1111-1111-1111-111111111111', "
            "'test-idempotency-key', 'contextual_cloze', 0, 0, '2026-08-31 12:00:00')"
        )
        connection.commit()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        progress_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(user_item_progress)"
            ).fetchall()
        }

    assert revision == ("20260831_0004",)
    assert "sm2_ease" not in progress_columns

    command.upgrade(config, "head")

    assert_t05_schema(database_path)
    with sqlite3.connect(database_path) as connection:
        progress_backfill = connection.execute(
            "SELECT dimension_scores, consecutive_successful_reviews, "
            "sm2_interval_days, sm2_ease, last_outcome FROM user_item_progress"
        ).fetchone()
        attempt_backfill = connection.execute(
            "SELECT skill_dimension, outcome, policy_version FROM review_attempts"
        ).fetchone()
        profile_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(learner_profiles)")
        }
    assert progress_backfill == ("{}", 0, 0, 2.5, None)
    assert "milestone_id" in profile_columns
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT milestone_id FROM learner_profiles WHERE user_id = 1"
        ).fetchone() == ("get-by",)
    assert attempt_backfill == (
        "grammar_application",
        "again",
        "t04-provisional",
    )
    get_settings.cache_clear()
