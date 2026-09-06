"""Tests for the presentation localizer: schemas, ordered parallel assembly,
per-phase routing (slides to the Japanese model, flow review to the structured
model), and deck parsing.
"""

import json
from threading import Lock

import pytest

from japanese_workplace_tutor.generation import (
    DeckFlowReview,
    LessonGenerationService,
    SlideInput,
    SlideLocalization,
)


def _flow_json() -> str:
    return DeckFlowReview(
        assessment="Put background before results.",
        recommended_order=(
            {"position": 1, "slide_title": "Background", "rationale": "context first"},
            {"position": 2, "slide_title": "Results", "rationale": "then the numbers"},
        ),
    ).model_dump_json()


class DeckTransport:
    """Keys each slide response to the slide's title, so ordered assembly can be
    verified regardless of the order parallel calls finish in."""

    def __init__(self, flow_json: str) -> None:
        self.flow_json = flow_json
        self.calls: list[str] = []
        self._lock = Lock()

    def generate(self, model_id, system_prompt, user_prompt, response_schema=None, timeout_seconds=None):
        with self._lock:
            self.calls.append(model_id)
        if "<deck>" in user_prompt:
            return self.flow_json
        data = json.loads(user_prompt.split("<slide>\n", 1)[1].split("\n</slide>")[0])
        title = data["title"]
        return SlideLocalization(
            japanese_title=f"[JA]{title}",
            japanese_body="本文です。",
            speaker_notes="Open humbly.",
            nuance_notes="Avoided katakana-English.",
        ).model_dump_json()


def test_slide_and_flow_schemas_validate() -> None:
    localization = SlideLocalization(
        japanese_title="売上の概要",
        japanese_body="第3四半期の売上は堅調。",
        speaker_notes="Start with a cushioning phrase.",
        nuance_notes="Used kengo for the client.",
    )
    assert localization.japanese_title
    review = DeckFlowReview(
        assessment="Move the conclusion later.",
        recommended_order=({"position": 1, "slide_title": "Intro", "rationale": "set context"},),
    )
    assert len(review.recommended_order) == 1


def test_localize_deck_preserves_order_and_routes_each_phase() -> None:
    slides = [
        SlideInput("Results", "Q3 revenue grew"),
        SlideInput("Risks", "Supply chain"),
        SlideInput("Next steps", "Expand to APAC"),
    ]
    transport = DeckTransport(_flow_json())
    service = LessonGenerationService(
        transport,
        "tsuzumi2",
        "gpt-5-nano",
        quiz_primary_model="gpt-5-nano",
        quiz_fallback_model="tsuzumi2",
    )

    deck = service.localize_deck(
        slides, {"audience": "client", "formality": "formal", "purpose": "sales pitch"}
    )

    # Ordered assembly: each localized slide matches its own input slide.
    assert [slide.japanese_title for slide in deck.slides] == [
        "[JA]Results",
        "[JA]Risks",
        "[JA]Next steps",
    ]
    # Slides localized on the Japanese (primary) model; flow review on the structured model.
    assert transport.calls.count("tsuzumi2") == 3
    assert transport.calls.count("gpt-5-nano") == 1
    assert deck.provider_name == "Tsuzumi 2"
    assert len(deck.flow_review.recommended_order) == 2


def test_localize_deck_rejects_empty() -> None:
    from japanese_workplace_tutor.generation import GenerationError

    service = LessonGenerationService(DeckTransport(_flow_json()), "tsuzumi2", "gpt-5-nano")
    with pytest.raises(GenerationError):
        service.localize_deck([], {})


def test_deck_parsing_from_pptx_and_paste() -> None:
    from japanese_workplace_tutor.app import _parse_pasted_deck, _parse_pptx_slides

    pasted = _parse_pasted_deck("Q3 Results\nRevenue grew 12%\n---\nNext Steps\nExpand")
    assert [(s.title, s.body) for s in pasted] == [
        ("Q3 Results", "Revenue grew 12%"),
        ("Next Steps", "Expand"),
    ]

    pptx = pytest.importorskip("pptx")
    import io

    presentation = pptx.Presentation()
    layout = presentation.slide_layouts[1]
    for title, body in (("Q3 Results", "Revenue grew"), ("Next Steps", "Expand")):
        slide = presentation.slides.add_slide(layout)
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    buffer = io.BytesIO()
    presentation.save(buffer)
    buffer.seek(0)

    parsed = _parse_pptx_slides(buffer)
    assert [s.title for s in parsed] == ["Q3 Results", "Next Steps"]
    assert "Revenue grew" in parsed[0].body
