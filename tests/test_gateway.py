"""The gateway tags every task and keeps PRIVATE content off external transports."""

import logging

import pytest

from japanese_workplace_tutor.core.errors import GenerationError
from japanese_workplace_tutor.core.ports import DataClass
from japanese_workplace_tutor.generation import LessonGenerationService
from japanese_workplace_tutor.llm.gateway import LLMGateway
from japanese_workplace_tutor.schemas.roleplay import RoleplayVerdict

VERDICT = (
    '{"goal_achieved": true, "goal_evidence": "e", "comprehensible": "yes",'
    ' "comprehensible_evidence": "e", "register_appropriate": true, "register_evidence": "e",'
    ' "recovered_from_curveball": "yes", "recovery_evidence": "e"}'
)


class CountingTransport:
    def __init__(self, accepts_private_data: bool = False) -> None:
        self.accepts_private_data = accepts_private_data
        self.calls = 0

    def generate(self, model_id, system_prompt, user_prompt, response_schema=None, timeout_seconds=None):
        self.calls += 1
        return VERDICT


def run(gateway: LLMGateway, data_class: DataClass):
    return gateway.generate_validated(
        RoleplayVerdict, "system", "user", "roleplay_judge", "failed", lambda response: response,
        data_class=data_class, prompt_version="test-v1",
    )


def test_private_content_is_refused_before_any_external_call() -> None:
    transport = CountingTransport()
    gateway = LLMGateway(transport, "tsuzumi-id", "gpt-id")

    with pytest.raises(GenerationError, match="on-premises"):
        run(gateway, DataClass.PRIVATE)
    assert transport.calls == 0


def test_private_content_runs_on_a_transport_that_opts_in() -> None:
    transport = CountingTransport(accepts_private_data=True)

    verdict, provider = run(LLMGateway(transport, "tsuzumi-id", "gpt-id"), DataClass.PRIVATE)

    assert verdict.goal_achieved is True
    assert transport.calls == 1


def test_public_tasks_log_phase_version_and_class(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("japanese_workplace_tutor.generation")
    logger.disabled = False
    caplog.set_level(logging.INFO, logger=logger.name)

    run(LLMGateway(CountingTransport(), "tsuzumi-id", "gpt-id"), DataClass.PUBLIC)

    assert "model_task phase=roleplay_judge prompt_version=test-v1 data_class=public" in caplog.text


def test_service_features_share_one_gateway() -> None:
    service = LessonGenerationService(CountingTransport(), "tsuzumi-id", "gpt-id")

    assert service.lessons._run.func.__self__ is service.gateway
    assert service.roleplay._run.func.__self__ is service.gateway
    assert service.presentation._run.func.__self__ is service.gateway
    assert service.lessons._run.keywords["data_class"] is DataClass.PUBLIC
