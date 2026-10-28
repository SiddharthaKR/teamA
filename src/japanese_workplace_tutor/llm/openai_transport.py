"""Adapter: OpenAI-compatible chat completions over HTTPS (strict JSON schema output)."""

import json
from urllib.parse import quote

import requests


def extract_json_text(content: str) -> str:
    """Recover a JSON document from a possibly noisy model response.

    Smaller models frequently wrap their JSON in markdown ```code fences``` or
    surround it with a sentence of prose, which then breaks ``json.loads``. This
    returns the outermost ``{...}`` or ``[...]`` span so parsing still succeeds.
    When no bracket is present the original text is returned unchanged, so the
    caller's ``json.loads`` still raises a clear, unaltered error.
    """

    text = content.strip()
    starts = [index for index in (text.find("{"), text.find("[")) if index != -1]
    if not starts:
        return text
    start = min(starts)
    close = "}" if text[start] == "{" else "]"
    end = text.rfind(close)
    if end <= start:
        return text
    return text[start : end + 1]


class OpenAICompatibleTransport:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 180.0) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()

    def generate(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        content = self._post_with_degrade(
            model_id, system_prompt, user_prompt, response_schema, timeout_seconds
        )
        return extract_json_text(content)

    def _post_with_degrade(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None,
        timeout_seconds: float | None,
    ) -> str:
        try:
            return self._request(
                model_id, system_prompt, user_prompt, response_schema, timeout_seconds
            )
        except requests.HTTPError as error:
            # Some OpenAI-compatible endpoints (notably smaller or local models such
            # as the primary) reject strict json_schema structured output with a 4xx.
            # Degrade once to plain json_object mode, describing the schema in the
            # prompt instead, rather than failing the whole attempt and burning a
            # fallback. A 5xx or a request without a schema is re-raised untouched.
            status = getattr(error.response, "status_code", None)
            if response_schema is None or status is None or not 400 <= status < 500:
                raise
            degraded_system = (
                system_prompt
                + "\n\nYour endpoint does not support schema-constrained output, so "
                "return a single JSON object that strictly conforms to this JSON "
                "schema, with no markdown fences or extra text:\n"
                + json.dumps(response_schema, ensure_ascii=False)
            )
            return self._request(
                model_id, degraded_system, user_prompt, None, timeout_seconds
            )

    def _request(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None,
        timeout_seconds: float | None,
    ) -> str:
        request_payload: dict[str, object] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        if response_schema is not None:
            request_payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "japanese_lesson_response",
                    "strict": True,
                    "schema": response_schema,
                },
            }
        if model_id.lower().startswith("gpt-5"):
            request_payload["reasoning_effort"] = "low"
        response = self._session.post(
            self._endpoint_for(model_id),
            headers=self._headers(),
            json=request_payload,
            timeout=timeout_seconds or self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Model response content is missing.")
        return content

    def _endpoint_for(self, model_id: str) -> str:
        return self._url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }


class AzureOpenAITransport(OpenAICompatibleTransport):
    """Azure v1 or deployment-based chat completions with API key auth."""

    def __init__(
        self, base_url: str, api_key: str, timeout_seconds: float = 180.0,
        api_version: str | None = None, *,
        apim_subscription_key: str | None = None,
        apim_subscription_key_header: str = "Ocp-Apim-Subscription-Key",
    ) -> None:
        super().__init__(base_url, api_key, timeout_seconds)
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._apim_subscription_key = apim_subscription_key
        self._apim_subscription_key_header = apim_subscription_key_header
        if api_version is None and not self._base_url.endswith("/openai/v1"):
            raise ValueError("Azure v1 endpoint must end in /openai/v1.")
        if api_version is not None and self._base_url.endswith("/openai/v1"):
            raise ValueError("Versioned Azure endpoint must use the resource root URL.")
        if api_version is not None and not api_version.strip():
            raise ValueError("Azure API version cannot be empty.")

    def _endpoint_for(self, model_id: str) -> str:
        if self._api_version is None:
            return f"{self._base_url}/chat/completions"
        deployment = quote(model_id, safe="")
        version = quote(self._api_version, safe="")
        return (
            f"{self._base_url}/openai/deployments/{deployment}/"
            f"chat/completions?api-version={version}"
        )

    def _headers(self) -> dict[str, str]:
        headers = {"api-key": self._api_key, "Content-Type": "application/json"}
        if self._apim_subscription_key:
            headers[self._apim_subscription_key_header] = self._apim_subscription_key
        return headers
