"""Export a review sheet for the team accuracy check (decision 9, method a).

Runs every lesson case in the golden set through the real generation service and
writes one row per dialogue line, target item and quiz question, with blank
"Correct?" and "Comment" columns for reviewers. Open the CSV in Excel.

    python scripts/export_review_sheet.py                 # offline mock (free)
    python scripts/export_review_sheet.py --live --limit 20   # real model, costs money

Only PUBLIC golden-set inputs are used, never learner data.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from japanese_workplace_tutor.generation import (  # noqa: E402
    GenerationError,
    LessonGenerationService,
    ScenarioMode,
)
from japanese_workplace_tutor.llm.mock import MockTransport  # noqa: E402
from japanese_workplace_tutor.llm.openai_transport import OpenAICompatibleTransport  # noqa: E402
from japanese_workplace_tutor.profile import JapaneseLevel, LevelSource, ProfileRecord  # noqa: E402
from japanese_workplace_tutor.prompts import lessons as lesson_prompts  # noqa: E402
from japanese_workplace_tutor.settings import Settings  # noqa: E402

COLUMNS = [
    "case_id", "learner_level", "role", "scenario", "kind", "id", "japanese", "reading",
    "english_or_meaning", "options", "answer_key", "key_source", "jlpt_level", "level_source",
    "stretch_share", "provider", "prompt_version", "toolkit", "Correct? (Y/N)", "Comment",
]


def _service(live: bool) -> LessonGenerationService:
    if not live:
        return LessonGenerationService(
            MockTransport(ROOT / "fixtures" / "llm"), "mock-primary", "mock-fallback"
        )
    settings = Settings()
    if not settings.model_configured or settings.model_api_key is None:
        raise SystemExit("--live needs JLT_MODEL_* settings in .env")
    return LessonGenerationService(
        OpenAICompatibleTransport(
            settings.model_base_url, settings.model_api_key.get_secret_value(),
            settings.model_timeout_seconds,
        ),
        settings.primary_model,
        settings.fallback_model,
        primary_timeout_seconds=settings.primary_model_timeout_seconds,
        quiz_primary_model=settings.quiz_primary_model or settings.fallback_model,
        quiz_fallback_model=settings.quiz_fallback_model or settings.primary_model,
    )


def _profile(case: dict) -> ProfileRecord:
    data = case["profile"]
    return ProfileRecord(
        user_id=0, role=data["role"], tasks=tuple(data["tasks"]), tools_domain=data["tools_domain"],
        declared_level=JapaneseLevel(data["level"]), estimated_working_level=None,
        level_source=LevelSource.SELF_REPORTED, level_confidence=1.0, romaji_preference=False,
    )


def rows_for_case(service: LessonGenerationService, case: dict) -> list[dict[str, object]]:
    learner = _profile(case)
    mode = ScenarioMode.EXPLAIN if case["mode"] == "explain" else ScenarioMode.GENERATE
    base = {
        "case_id": case["id"], "learner_level": learner.declared_level.value, "role": learner.role,
        "scenario": case["scenario"][:200], "prompt_version": lesson_prompts.PROMPT_VERSION,
        "toolkit": service.toolkit.version,
    }
    try:
        draft = service.generate_lesson_content(case["scenario"], mode, learner)
        quiz = service.generate_quiz(draft.content)
    except GenerationError as error:
        return [{**base, "kind": "generation_failed", "english_or_meaning": str(error)}]
    stretch = f"{draft.difficulty.stretch_share:.0%}" if draft.difficulty else ""
    rows: list[dict[str, object]] = []
    for number, line in enumerate(draft.line_explanations, start=1):
        rows.append({**base, "kind": "line", "id": f"line-{number}", "japanese": line.japanese_text,
                     "english_or_meaning": line.english_meaning, "stretch_share": stretch,
                     "provider": draft.provider_name})
    for item in draft.content.items:
        rows.append({**base, "kind": "item", "id": item.canonical_id, "japanese": item.expression,
                     "reading": item.reading, "english_or_meaning": item.meaning,
                     "jlpt_level": item.jlpt_level or "unrated", "level_source": item.jlpt_provenance,
                     "provider": draft.provider_name})
    for question in (*quiz.questions, *quiz.retry_questions):
        rows.append({**base, "kind": "question", "id": question.question_id,
                     "japanese": question.prompt, "options": " | ".join(question.options),
                     "answer_key": question.options[question.correct_option_index],
                     "key_source": question.key_source.value,
                     "english_or_meaning": question.explanation, "provider": quiz.provider_name})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="call the configured model (costs money)")
    parser.add_argument("--limit", type=int, default=None, help="only the first N lesson cases")
    parser.add_argument("--golden", type=Path, default=ROOT / "evals" / "golden" / "v0.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "review-sheets" / "review_sheet.csv")
    args = parser.parse_args()

    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    cases = [case for case in golden["cases"] if case["feature"] == "lesson"][: args.limit]
    service = _service(args.live)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.out.open("w", encoding="utf-8-sig", newline="") as handle:  # BOM: Excel shows Japanese
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            for row in rows_for_case(service, case):
                writer.writerow(row)
                count += 1
    print(f"Wrote {count} rows for {len(cases)} cases to {args.out}")


if __name__ == "__main__":
    main()
