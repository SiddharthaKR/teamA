"""Preview and persist public, learner-chosen words and grammar points."""

from dataclasses import dataclass
import re
import unicodedata

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from .core.japanese import contains_japanese
from .core.language import LanguageToolkit
from .models import PersonalTerm

_GRADE = re.compile(r"^([SAB])\s+(.+)$")


class TermValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TermPreview:
    kind: str
    expression: str
    meaning: str | None
    importance: str
    status: str
    reference_id: str | None
    reading: str | None


class PersonalTermService:
    def __init__(self, engine: Engine, toolkit: LanguageToolkit) -> None:
        self._engine = engine
        self._toolkit = toolkit

    def list_terms(self, user_id: int) -> tuple[PersonalTerm, ...]:
        with Session(self._engine) as session:
            return tuple(session.scalars(
                select(PersonalTerm).where(PersonalTerm.user_id == user_id)
                .order_by(PersonalTerm.created_at, PersonalTerm.id)
            ).all())

    def preview(
        self, user_id: int, pasted: str, *, kind: str = "word", importance: str = "A"
    ) -> tuple[TermPreview, ...]:
        if kind not in {"word", "grammar"} or importance not in {"S", "A", "B"}:
            raise TermValidationError("Choose a valid kind and importance.")
        lines = [line.strip() for line in pasted.splitlines() if line.strip()]
        if len(lines) > 500:
            raise TermValidationError("Paste at most 500 lines at once.")
        existing = {(term.kind, term.expression) for term in self.list_terms(user_id)}
        seen: set[tuple[str, str]] = set()
        result = []
        for line in lines:
            line = unicodedata.normalize("NFKC", line)
            grade_match = _GRADE.match(line)
            grade = grade_match.group(1) if grade_match else importance
            body = grade_match.group(2) if grade_match else line
            parts = re.split(r"[,、]", body, maxsplit=1)
            expression = parts[0].strip()
            meaning = parts[1].strip() if len(parts) > 1 else None
            key = kind, expression
            status = "ready"
            reference_id = None
            reading = None
            if len(line) > 100 or not contains_japanese(expression) or not expression:
                status = "rejected"
            elif key in existing or key in seen:
                status = "duplicate"
            elif kind == "grammar":
                point = self._toolkit.grammar_point(expression)
                reference_id = point.id if point else None
                if point is None:
                    status = "unverified"
            else:
                entry = self._toolkit.lookup(expression)
                reference_id = entry.lemma if entry else None
                reading = sorted(entry.readings)[0] if entry and entry.readings else None
                if entry is None:
                    status = "unverified"
            seen.add(key)
            result.append(TermPreview(kind, expression, meaning, grade, status,
                                      reference_id, reading))
        return tuple(result)

    def save(
        self, user_id: int, preview: tuple[TermPreview, ...], *, public_confirmed: bool
    ) -> int:
        if not public_confirmed:
            raise TermValidationError("Confirm these terms contain only public content.")
        to_save = [term for term in preview if term.status in {"ready", "unverified"}]
        with Session(self._engine) as session:
            existing = {
                (kind, expression) for kind, expression in session.execute(
                    select(PersonalTerm.kind, PersonalTerm.expression)
                    .where(PersonalTerm.user_id == user_id)
                )
            }
            to_save = [term for term in to_save
                       if (term.kind, term.expression) not in existing]
            count = len(existing)
            if count + len(to_save) > 2000:
                raise TermValidationError("A personal list can contain at most 2,000 terms.")
            for term in to_save:
                session.add(PersonalTerm(
                    user_id=user_id, kind=term.kind, expression=term.expression,
                    reference_id=term.reference_id, reading=term.reading,
                    meaning=term.meaning, importance=term.importance,
                    status="active", source="pasted",
                ))
            session.commit()
        return len(to_save)

    def set_importance(self, user_id: int, term_id: int, importance: str) -> bool:
        if importance not in {"S", "A", "B"}:
            raise TermValidationError("Choose S, A or B importance.")
        with Session(self._engine) as session:
            term = session.scalar(select(PersonalTerm).where(
                PersonalTerm.id == term_id, PersonalTerm.user_id == user_id
            ))
            if term is None:
                return False
            term.importance = importance
            session.commit()
            return True

    def set_hidden(self, user_id: int, term_id: int, hidden: bool) -> bool:
        with Session(self._engine) as session:
            term = session.scalar(select(PersonalTerm).where(
                PersonalTerm.id == term_id, PersonalTerm.user_id == user_id
            ))
            if term is None:
                return False
            term.status = "hidden" if hidden else "active"
            session.commit()
            return True
