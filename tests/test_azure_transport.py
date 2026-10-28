from unittest.mock import Mock
import pytest

from japanese_workplace_tutor.llm.openai_transport import AzureOpenAITransport
from japanese_workplace_tutor.settings import Settings


def test_azure_deployment_request_uses_deployment_route_and_api_key_header() -> None:
    transport = AzureOpenAITransport(
        "https://team.openai.azure.com", "test-key", api_version="2024-10-21"
    )
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    transport._session.post = Mock(return_value=response)

    assert transport.generate("lesson-deployment", "system", "user") == '{"ok": true}'
    args, kwargs = transport._session.post.call_args
    assert args[0] == (
        "https://team.openai.azure.com/openai/deployments/lesson-deployment/"
        "chat/completions?api-version=2024-10-21"
    )
    assert kwargs["headers"]["api-key"] == "test-key"
    assert "Authorization" not in kwargs["headers"]


def test_azure_v1_request_uses_model_deployment_name() -> None:
    transport = AzureOpenAITransport("https://team.openai.azure.com/openai/v1", "test-key")
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    transport._session.post = Mock(return_value=response)

    transport.generate("lesson-deployment", "system", "user")
    args, kwargs = transport._session.post.call_args
    assert args[0] == "https://team.openai.azure.com/openai/v1/chat/completions"
    assert kwargs["json"]["model"] == "lesson-deployment"
    assert kwargs["headers"]["api-key"] == "test-key"


def test_azure_v1_can_send_apim_key_in_configured_header() -> None:
    transport = AzureOpenAITransport(
        "https://gateway.azure-api.net/ai/openai/v1", "backend-key",
        apim_subscription_key="gateway-key",
        apim_subscription_key_header="Authorization",
    )
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    transport._session.post = Mock(return_value=response)

    transport.generate("lesson-deployment", "system", "user")
    _, kwargs = transport._session.post.call_args
    assert kwargs["headers"]["api-key"] == "backend-key"
    assert kwargs["headers"]["Authorization"] == "gateway-key"


def test_azure_configuration_requires_route_and_key(monkeypatch) -> None:
    for name in ("JLT_MODEL_BASE_URL", "JLT_MODEL_API_KEY", "JLT_PRIMARY_MODEL", "JLT_FALLBACK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(
        model_provider="azure",
        model_base_url="https://team.openai.azure.com",
        model_api_key="test-key",
        primary_model="lesson-deployment",
        fallback_model="lesson-deployment",
        _env_file=None,
    )
    assert settings.model_configured is False

    settings = Settings(
        model_provider="azure",
        model_base_url="https://team.openai.azure.com/openai/v1",
        model_api_key="test-key",
        primary_model="lesson-deployment",
        fallback_model="lesson-deployment",
        _env_file=None,
    )
    assert settings.model_configured is True


def test_azure_rejects_v1_url_with_legacy_api_version() -> None:
    with pytest.raises(ValueError, match="resource root"):
        AzureOpenAITransport(
            "https://team.openai.azure.com/openai/v1", "test-key",
            api_version="2024-10-21",
        )
