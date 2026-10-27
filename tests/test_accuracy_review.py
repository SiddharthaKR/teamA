"""Decision 9 tools: reviewer verdicts, accuracy report, review sheet export and scoring."""

import csv
import json
from pathlib import Path
import subprocess
import sys

from japanese_workplace_tutor.generation import LessonGenerationService, ScenarioMode
from japanese_workplace_tutor.lesson import ActiveLesson, LessonService
from japanese_workplace_tutor.llm.mock import MockTransport
from japanese_workplace_tutor.models import Base
from japanese_workplace_tutor.review import ReviewService, review_targets

from test_generation import profile
from test_lesson import create_services

ROOT = Path(__file__).resolve().parents[1]


def generated_active(lessons: LessonService, user_id: int) -> ActiveLesson:
    service = LessonGenerationService(MockTransport(ROOT / "fixtures" / "llm"), "mock-primary", "mock-fallback")
    draft = service.generate_lesson_content("", ScenarioMode.GENERATE, profile())
    active_draft = lessons.start_generated_lesson_draft(user_id, draft)
    return lessons.activate_generated_quiz(active_draft, service.generate_quiz(draft.content))


def test_verdicts_upsert_and_feed_the_report(tmp_path: Path) -> None:
    auth, lessons, engine = create_services(tmp_path / "review.db")
    Base.metadata.create_all(engine)
    user = auth.register("Reviewer", "correct horse battery staple")
    active = generated_active(lessons, user.id)
    targets = review_targets(active)
    reviews = ReviewService(engine)
    questions = [t for t in targets if t.kind == "question"]
    items = [t for t in targets if t.kind == "item"]

    reviews.record(user.id, active.lesson_session_id, questions[0], "wrong", reason="wrong_answer_key")
    reviews.record(user.id, active.lesson_session_id, questions[0], "ok")  # re-review overwrites
    reviews.record(user.id, active.lesson_session_id, questions[1], "wrong", reason="ambiguous_question")
    reviews.record(user.id, active.lesson_session_id, items[0], "ok", versions={"prompts": {"lessons": "lessons-v1"}})
    report = reviews.report()

    assert {t.kind for t in targets} == {"line", "item", "question"}
    assert report.reviewed == 3
    assert report.wrong == 1
    assert report.by_kind["question"] == (1, 2)
    assert report.by_key_source["derived"] == (1, 2)
    assert report.by_reason == {"ambiguous_question": 1}
    engine.dispose()


def test_review_sheet_export_and_scoring(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.csv"
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_review_sheet.py"), "--limit", "3", "--out", str(sheet)],
        capture_output=True, text=True, timeout=120, cwd=ROOT,
    )
    assert run.returncode == 0, run.stderr
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["kind"] for row in rows} == {"line", "item", "question"}
    assert {row["key_source"] for row in rows if row["kind"] == "question"} == {"derived", "unverified"}

    for row in rows:
        row["Correct? (Y/N)"] = "N" if row["id"] == "q-kaigi-meaning" else "Y"
    with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    scored = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "score_review_sheet.py"), str(sheet), "--target", "0.5"],
        capture_output=True, text=True, timeout=60,
    )
    assert scored.returncode == 0, scored.stdout + scored.stderr
    assert "question:derived" in scored.stdout
    assert json.dumps("Graded answer keys")[1:-1] in scored.stdout
