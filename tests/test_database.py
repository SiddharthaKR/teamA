from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from japanese_workplace_tutor.database import check_database, create_database_engine
from japanese_workplace_tutor.settings import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_database_is_ready_with_foreign_keys_enabled(tmp_path: Path) -> None:
    settings = Settings(database_url=sqlite_url(tmp_path / "app.db"), _env_file=None)
    engine = create_database_engine(settings)

    health = check_database(engine)
    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
    engine.dispose()

    assert health.ready is True
    assert health.foreign_keys_enabled is True
    assert foreign_keys == 1


def test_foreign_keys_are_enabled_on_each_connection(tmp_path: Path) -> None:
    settings = Settings(database_url=sqlite_url(tmp_path / "app.db"), _env_file=None)
    engine = create_database_engine(settings)

    with engine.connect() as first:
        assert first.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    engine.dispose()

    engine = create_database_engine(settings)
    with engine.connect() as second:
        assert second.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    engine.dispose()


def test_create_database_engine_upgrades_a_stale_local_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["database_url"] = sqlite_url(database_path)
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    command.upgrade(config, "20260831_0005")

    settings = Settings(database_url=sqlite_url(database_path), _env_file=None)
    engine = create_database_engine(settings, PROJECT_ROOT)

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        attempt_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(review_attempts)").fetchall()
        }
    engine.dispose()

    assert revision == ("20261024_0009",)
    assert "answer_confidence" in attempt_columns
