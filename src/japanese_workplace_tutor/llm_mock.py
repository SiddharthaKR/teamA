"""Offline model transports: replay fixtures without keys, or record live responses.

Both classes implement the existing ``ModelTransport`` protocol, so the generation
service, its validators and its fallback policy run unchanged on top of them.

* ``MockTransport`` answers from JSON fixture files and never touches the network.
  It powers tests, CI and an offline demo (``JLT_LLM_MODE=mock``).
* ``RecordingTransport`` wraps a live transport and appends every response to a
  JSONL file (``JLT_LLM_MODE=record``) so real outputs can later become fixtures.
  Recordings include prompts and responses, so only record PUBLIC inputs such as
  the golden set - never learner-supplied private text.

Fixture layout: one file per response schema, named after the schema title (the
Pydantic class name), e.g. ``fixtures/llm/GeneratedQuizPackage.json``::

    [
      {"match": ["Write exactly 6 dialogue lines"], "response": {...}},
      {"match": [], "response": {...}}
    ]

The first entry whose ``match`` substrings all occur in the system or user prompt
wins, so put specific entries before a catch-all entry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock

from japanese_workplace_tutor.generation import ModelTransport


class MockFixtureMissing(RuntimeError):
    """No fixture matched a request; the service treats it as a technical failure."""


@dataclass(frozen=True)
class MockCall:
    schema_title: str
    model_id: str
    matched: bool


@dataclass
class MockTransport:
    """Replay fixture responses keyed by schema title and prompt substrings."""

    fixture_dir: Path
    calls: list[MockCall] = field(default_factory=list)
    _cache: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def generate(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        title = schema_title(response_schema)
        prompt = f"{system_prompt}\n{user_prompt}"
        for entry in self._entries(title):
            needles = entry.get("match", [])
            if isinstance(needles, list) and all(
                isinstance(needle, str) and needle in prompt for needle in needles
            ):
                self._record(MockCall(title, model_id, matched=True))
                return json.dumps(entry["response"], ensure_ascii=False)
        self._record(MockCall(title, model_id, matched=False))
        raise MockFixtureMissing(f"No mock fixture matches schema '{title}'.")

    def _entries(self, title: str) -> list[dict[str, object]]:
        with self._lock:
            if title not in self._cache:
                path = Path(self.fixture_dir) / f"{title}.json"
                entries = (
                    json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
                )
                if not isinstance(entries, list):
                    raise ValueError(f"Fixture file {path.name} must contain a JSON list.")
                self._cache[title] = entries
            return self._cache[title]

    def _record(self, call: MockCall) -> None:
        with self._lock:
            self.calls.append(call)


@dataclass
class RecordingTransport:
    """Delegate to a live transport and append each successful response to JSONL."""

    inner: ModelTransport
    output_path: Path
    _lock: Lock = field(default_factory=Lock)

    def generate(
        self,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        response = self.inner.generate(
            model_id, system_prompt, user_prompt, response_schema, timeout_seconds
        )
        record = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "schema_title": schema_title(response_schema),
            "model_id": model_id,
            "prompt_sha256": sha256(
                f"{system_prompt}\n{user_prompt}".encode("utf-8")
            ).hexdigest(),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": response,
        }
        path = Path(self.output_path)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return response


def schema_title(response_schema: dict[str, object] | None) -> str:
    if not response_schema:
        return "untyped"
    title = response_schema.get("title")
    return title if isinstance(title, str) and title else "untyped"


def load_fixture_titles(fixture_dir: Path) -> Sequence[str]:
    """List the schema titles that have fixtures, for health checks and tests."""

    return tuple(sorted(path.stem for path in Path(fixture_dir).glob("*.json")))
