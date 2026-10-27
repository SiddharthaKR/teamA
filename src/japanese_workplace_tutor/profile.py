"""Validated, user-scoped learner profile persistence."""

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .core.learner import JapaneseLevel, LevelSource, ProfileRecord  # noqa: F401 (re-exported)
from .models import LearnerProfile

MAX_ROLE_LENGTH = 256
MAX_TASK_LENGTH = 256
MAX_TOOLS_DOMAIN_LENGTH = 2000

ROLE_TASK_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "Software engineer": (
        "Discuss requirements",
        "Give status updates",
        "Review technical designs",
    ),
    "Project manager": (
        "Run project meetings",
        "Coordinate schedules",
        "Report risks and progress",
    ),
    "Sales representative": (
        "Understand customer needs",
        "Present proposals",
        "Follow up with customers",
    ),
    "Human resources": (
        "Support employee onboarding",
        "Explain workplace policies",
        "Coordinate interviews",
    ),
    "Researcher": (
        "Discuss research findings",
        "Plan experiments",
        "Present technical results",
    ),
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise ValueError("Control characters are not allowed.")
    return normalized


class ProfileInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: str = Field(max_length=MAX_ROLE_LENGTH)
    tasks: list[str]
    tools_domain: str | None = Field(default=None, max_length=MAX_TOOLS_DOMAIN_LENGTH)
    declared_level: JapaneseLevel
    romaji_preference: bool = False

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = _normalize_text(value)
        if not normalized:
            raise ValueError("Role or title is required.")
        return normalized

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, values: list[str]) -> list[str]:
        normalized_tasks: list[str] = []
        for value in values:
            normalized = _normalize_text(value)
            if not normalized:
                continue
            if len(normalized) > MAX_TASK_LENGTH:
                raise ValueError(
                    f"Each typical task must be at most {MAX_TASK_LENGTH} characters."
                )
            if normalized not in normalized_tasks:
                normalized_tasks.append(normalized)
        if not normalized_tasks:
            raise ValueError("Add at least one typical task.")
        return normalized_tasks

    @field_validator("tools_domain")
    @classmethod
    def validate_tools_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        return normalized or None


class ProfileValidationError(ValueError):
    pass


class ProfileNotFoundError(LookupError):
    pass


class ProfileAlreadyExistsError(ValueError):
    pass


def _validated_input(**values: object) -> ProfileInput:
    try:
        return ProfileInput.model_validate(values)
    except ValidationError as error:
        messages = [item["msg"].removeprefix("Value error, ") for item in error.errors()]
        raise ProfileValidationError(" ".join(messages)) from error


def _to_record(profile: LearnerProfile) -> ProfileRecord:
    return ProfileRecord(
        user_id=profile.user_id,
        role=profile.role,
        tasks=tuple(profile.tasks),
        tools_domain=profile.tools_domain,
        declared_level=JapaneseLevel(profile.declared_level),
        estimated_working_level=(
            JapaneseLevel(profile.estimated_working_level)
            if profile.estimated_working_level
            else None
        ),
        level_source=LevelSource(profile.level_source),
        level_confidence=profile.level_confidence,
        romaji_preference=profile.romaji_preference,
    )


class ProfileService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_profile(self, user_id: int) -> ProfileRecord | None:
        with Session(self._engine) as session:
            profile = session.scalar(
                select(LearnerProfile).where(LearnerProfile.user_id == user_id)
            )
            return _to_record(profile) if profile is not None else None

    def create_profile(
        self,
        user_id: int,
        *,
        role: str,
        tasks: list[str],
        declared_level: JapaneseLevel | str,
        tools_domain: str | None = None,
        romaji_preference: bool = False,
    ) -> ProfileRecord:
        profile_input = _validated_input(
            role=role,
            tasks=tasks,
            tools_domain=tools_domain,
            declared_level=declared_level,
            romaji_preference=romaji_preference,
        )
        profile = LearnerProfile(
            user_id=user_id,
            role=profile_input.role,
            tasks=profile_input.tasks,
            tools_domain=profile_input.tools_domain,
            declared_level=profile_input.declared_level.value,
            level_source=LevelSource.SELF_REPORTED.value,
            level_confidence=1.0,
            romaji_preference=profile_input.romaji_preference,
        )
        try:
            with Session(self._engine) as session:
                session.add(profile)
                session.commit()
                session.refresh(profile)
                return _to_record(profile)
        except IntegrityError as error:
            raise ProfileAlreadyExistsError(
                "A learner profile already exists for this account."
            ) from error

    def update_profile(
        self,
        user_id: int,
        *,
        role: str,
        tasks: list[str],
        declared_level: JapaneseLevel | str,
        tools_domain: str | None = None,
        romaji_preference: bool = False,
    ) -> ProfileRecord:
        profile_input = _validated_input(
            role=role,
            tasks=tasks,
            tools_domain=tools_domain,
            declared_level=declared_level,
            romaji_preference=romaji_preference,
        )
        with Session(self._engine) as session:
            profile = session.scalar(
                select(LearnerProfile).where(LearnerProfile.user_id == user_id)
            )
            if profile is None:
                raise ProfileNotFoundError("Learner profile not found.")
            profile.role = profile_input.role
            profile.tasks = profile_input.tasks
            profile.tools_domain = profile_input.tools_domain
            profile.declared_level = profile_input.declared_level.value
            profile.romaji_preference = profile_input.romaji_preference
            session.commit()
            session.refresh(profile)
            return _to_record(profile)