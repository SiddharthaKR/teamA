"""Team accuracy review (decision 9): verdicts on generated content and the error rate.

Reviewer mode only (JLT_REVIEWER_MODE=true). Each verdict keeps a snapshot of
what the reviewer judged and the versions that produced it, so a wrong answer
key can be traced to a prompt version, a model and a reference-data version.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from .lesson import ActiveLesson
from .models import ContentReview

REASONS = {
    "wrong_answer_key": "Answer key is wrong",
    "ambiguous_question": "More than one option is right",
    "wrong_reading": "Reading / furigana is wrong",
    "wrong_meaning": "Meaning or translation is wrong",
    "wrong_level": "JLPT level is wrong",
    "unnatural_japanese": "Japanese is unnatural or wrong register",
    "other": "Other",
}


@dataclass(frozen=True)
class ReviewTarget:
    kind: str  # item | question | line
    target_id: str
    label: str
    snapshot: dict[str, object]


def review_targets(active: ActiveLesson) -> tuple[ReviewTarget, ...]:
    lesson = active.lesson
    targets: list[ReviewTarget] = []
    for number, line in enumerate(active.line_explanations, start=1):
        targets.append(
            ReviewTarget(
                "line",
                f"line-{number}",
                f"Line {number}: {line.japanese_text} — {line.english_meaning}",
                {"japanese": line.japanese_text, "english": line.english_meaning},
            )
        )
    for item in lesson.items:
        targets.append(
            ReviewTarget(
                "item",
                item.canonical_id,
                f"{item.expression} ({item.reading}) — {item.meaning} · "
                f"{item.jlpt_level or 'unrated'} [{item.jlpt_provenance}]",
                item.model_dump(mode="json"),
            )
        )
    for question in (*lesson.questions, *active.retry_questions):
        key = question.options[question.correct_option_index]
        targets.append(
            ReviewTarget(
                "question",
                question.question_id,
                f"{question.prompt} → {key}  ({question.key_source.value})",
                {**question.model_dump(mode="json"), "key_source": question.key_source.value},
            )
        )
    return tuple(targets)


@dataclass(frozen=True)
class AccuracyReport:
    reviewed: int
    wrong: int
    by_kind: dict[str, tuple[int, int]] = field(default_factory=dict)  # kind -> (wrong, reviewed)
    by_key_source: dict[str, tuple[int, int]] = field(default_factory=dict)
    by_reason: dict[str, int] = field(default_factory=dict)
    wrong_rows: tuple[dict[str, object], ...] = ()

    @property
    def error_rate(self) -> float:
        return self.wrong / self.reviewed if self.reviewed else 0.0


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ReviewService:
    def __init__(self, engine: Engine, clock: Callable[[], datetime] = _utc_now) -> None:
        self._engine = engine
        self._clock = clock

    def record(
        self,
        user_id: int,
        lesson_session_id: str,
        target: ReviewTarget,
        verdict: str,
        *,
        reason: str | None = None,
        note: str | None = None,
        versions: dict[str, object] | None = None,
    ) -> None:
        if verdict not in ("ok", "wrong"):
            raise ValueError("Verdict must be 'ok' or 'wrong'.")
        if reason is not None and reason not in REASONS:
            raise ValueError("Unknown review reason.")
        with Session(self._engine) as session:
            row = session.scalar(
                select(ContentReview).where(
                    ContentReview.user_id == user_id,
                    ContentReview.lesson_session_id == lesson_session_id,
                    ContentReview.target_kind == target.kind,
                    ContentReview.target_id == target.target_id,
                )
            )
            if row is None:
                row = ContentReview(
                    user_id=user_id,
                    lesson_session_id=lesson_session_id,
                    target_kind=target.kind,
                    target_id=target.target_id,
                )
                session.add(row)
            row.verdict = verdict
            row.reason = reason if verdict == "wrong" else None
            row.note = (note or "").strip()[:500] or None
            row.snapshot = target.snapshot
            row.versions = versions or {}
            row.reviewed_at = self._clock()
            session.commit()

    def all_reviews(self) -> tuple[ContentReview, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(select(ContentReview).order_by(ContentReview.reviewed_at)).all()
            session.expunge_all()
            return tuple(rows)

    def report(self) -> AccuracyReport:
        return build_report(self.all_reviews())


def build_report(rows: Sequence[ContentReview]) -> AccuracyReport:
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_source: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    reasons: Counter[str] = Counter()
    wrong_rows = []
    for row in rows:
        is_wrong = row.verdict == "wrong"
        by_kind[row.target_kind][0] += is_wrong
        by_kind[row.target_kind][1] += 1
        if row.target_kind == "question":
            source = str((row.snapshot or {}).get("key_source", "unknown"))
            by_source[source][0] += is_wrong
            by_source[source][1] += 1
        if is_wrong:
            reasons[row.reason or "other"] += 1
            wrong_rows.append(
                {
                    "kind": row.target_kind,
                    "target": row.target_id,
                    "reason": row.reason,
                    "note": row.note,
                    "snapshot": row.snapshot,
                    "versions": row.versions,
                }
            )
    return AccuracyReport(
        reviewed=len(rows),
        wrong=sum(row.verdict == "wrong" for row in rows),
        by_kind={kind: (w, n) for kind, (w, n) in by_kind.items()},
        by_key_source={source: (w, n) for source, (w, n) in by_source.items()},
        by_reason=dict(reasons),
        wrong_rows=tuple(wrong_rows),
    )
