"""Typed, environment-only application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
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
    apim_subscription_key: SecretStr | None = None
    apim_subscription_key_header: str = "Ocp-Apim-Subscription-Key"
    model_provider: Literal["openai-compatible", "azure"] = "openai-compatible"
    azure_api_version: str | None = None
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

    @field_validator("apim_subscription_key_header")
    @classmethod
    def validate_apim_header(cls, value: str) -> str:
        import re
        value = value.strip()
        if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", value):
            raise ValueError("APIM subscription key header must be a valid HTTP header name.")
        return value

    @property
    def model_configured(self) -> bool:
        """Return whether every setting required for future model calls exists."""

        credentials_ready = bool(
            self.model_base_url
            and (self.model_api_key or self.apim_subscription_key)
            and self.primary_model
            and self.fallback_model
        )
        if not credentials_ready:
            return False
        if self.model_provider == "azure":
            assert self.model_base_url is not None
            is_v1_url = self.model_base_url.rstrip("/").endswith("/openai/v1")
            return is_v1_url != bool(self.azure_api_version)
        return True

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
