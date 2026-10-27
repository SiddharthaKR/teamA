"""Typed, environment-only application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secret values are masked by Pydantic."""

    model_config = SettingsConfigDict(
        env_prefix="JLT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Japanese Workplace Learning"
    database_url: str = "sqlite:///data/app.db"
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    primary_model: str | None = None
    fallback_model: str | None = None
    # Per-phase routing for the strict-JSON quiz step. The primary model is strong at
    # Japanese but weak at rigid quiz JSON, so the quiz phase defaults to the fallback
    # (structured) model, then falls back to the primary. Set either to override.
    quiz_primary_model: str | None = None
    quiz_fallback_model: str | None = None
    model_timeout_seconds: float = 180.0
    primary_model_timeout_seconds: float = 150.0
    # None keeps the strictly sequential primary-then-fallback route.
    hedge_after_seconds: float | None = None
    # Trades more provider requests for lower wall-clock latency.
    parallel_explanations: bool = False
    explanation_workers: int = 4
    # "live" calls the configured endpoint; "mock" replays offline fixtures and needs
    # no credentials; "record" calls the endpoint and appends every response to
    # llm_recording_path so PUBLIC golden-set outputs can become fixtures.
    llm_mode: Literal["live", "mock", "record"] = "live"
    mock_fixture_dir: str = "fixtures/llm"
    llm_recording_path: str = "data/llm-recordings/recordings.jsonl"
    # Team accuracy review (decision 9): shows "right / wrong" controls on generated
    # content and an Accuracy page. For reviewers only; snapshots keep reviewed text.
    reviewer_mode: bool = False

    @property
    def model_configured(self) -> bool:
        """Return whether every setting required for future model calls exists."""

        return all(
            (
                self.model_base_url,
                self.model_api_key,
                self.primary_model,
                self.fallback_model,
            )
        )

    @property
    def generation_available(self) -> bool:
        """Return whether model-backed features can run (live/record keys, or mock mode)."""

        return self.llm_mode == "mock" or self.model_configured

    @property
    def model_status(self) -> str:
        """Return a safe diagnostic that never contains configuration values."""

        return "Configured" if self.model_configured else "Not configured"

    def ensure_local_directories(self, project_root: Path | None = None) -> None:
        """Create the parent directory for a relative local SQLite database."""

        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix) or self.database_url.startswith("sqlite:////"):
            return
        database_path = Path(self.database_url.removeprefix(prefix))
        if str(database_path) == ":memory:":
            return
        root = project_root or Path.cwd()
        (root / database_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache settings for one application process."""

    return Settings()
