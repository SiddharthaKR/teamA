"""Ports: the only interfaces the domain and features use to reach the outside world."""

from enum import StrEnum
from typing import Protocol


class ModelTransport(Protocol):
    def generate(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> str: ...


class DataClass(StrEnum):
    """Who may see a prompt's content. Every model task is tagged with one.

    PUBLIC: generic or user-attested non-confidential content; may go to an external API.
    PRIVATE: learner documents or work data; only an on-premises transport may receive it.
    """

    PUBLIC = "public"
    PRIVATE = "private"


def accepts_private_data(transport: object) -> bool:
    """Transports opt in to PRIVATE content explicitly; external APIs never do."""

    return bool(getattr(transport, "accepts_private_data", False))
