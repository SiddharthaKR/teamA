"""Versioned situation vocabulary selected locally before model generation."""

from datetime import datetime
from functools import lru_cache
from importlib.resources import files
import json

from .core.difficulty import LEARNER_RANK
from .core.items import ItemCategory
from .core.language import LEVEL_RANK, LanguageToolkit
from .core.learner import ProfileRecord
from .core.priority import Candidate, RankedTarget, rank_targets
from .core.progress import ProgressRecord
from .features.lessons import canonical_item_id


@lru_cache(maxsize=1)
def _situation_data() -> dict:
    path = files("japanese_workplace_tutor.resources").joinpath(
        "situation_words_v1.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


class SituationWordService:
    def __init__(self, toolkit: LanguageToolkit) -> None:
        self._toolkit = toolkit
        self._situations = tuple(_situation_data()["situations"])

    def validate_references(self) -> tuple[str, ...]:
        """Report words that no longer resolve to the curated workplace lexicon."""
        missing = []
        for situation in self._situations:
            for expression in situation["words"]:
                entry = self._toolkit.lookup(expression)
                if entry is None or not entry.business_group:
                    missing.append(f"{situation['id']}: {expression}")
        return tuple(missing)

    def match(self, scenario: str) -> str | None:
        text = scenario.casefold()
        matches = [
            (len(trigger), -index, situation["id"])
            for index, situation in enumerate(self._situations)
            for trigger in situation["triggers"]
            if trigger.casefold() in text
        ]
        return max(matches)[2] if matches else None

    def lesson_targets(
        self, scenario: str, profile: ProfileRecord,
        progress: tuple[ProgressRecord, ...], now: datetime,
    ) -> tuple[RankedTarget, ...]:
        situation_id = self.match(scenario)
        situation = next((row for row in self._situations
                          if row["id"] == situation_id), None)
        if situation is None:
            return ()
        learner_rank = LEARNER_RANK[profile.estimated_working_level or profile.declared_level]
        by_id = {row.item_id: row for row in progress}
        candidates = []
        for position, expression in enumerate(situation["words"]):
            entry = self._toolkit.lookup(expression)
            if entry is None or not entry.business_group:
                continue
            item_id = canonical_item_id(ItemCategory.VOCABULARY, expression, self._toolkit)
            history = by_id.get(item_id)
            due = bool(history and history.next_review_at and history.next_review_at <= now)
            if history and history.mastery_score >= 0.8 and not due:
                continue
            eligible = bool(entry.level and LEVEL_RANK[entry.level] <= learner_rank + 1)
            candidates.append(Candidate(
                item_id, expression, 0.0, 1.0, 0.0,
                1.0 - position / len(situation["words"]), "A",
                history.mastery_score if history else 0.0, eligible, due,
            ))
        ranked = rank_targets(tuple(candidates), limit=len(candidates), due_limit=1)
        position = {row.item_id: index for index, row in enumerate(ranked)}
        return tuple(sorted(ranked, key=lambda row: (
            0 if any(candidate.item_id == row.item_id and candidate.due
                     for candidate in candidates) else 1,
            by_id[row.item_id].exposure_count if row.item_id in by_id else 0,
            position[row.item_id],
        ))[:2])
