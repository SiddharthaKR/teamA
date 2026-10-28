"""Reference-backed draft domain packs for blank workplace lessons."""

from datetime import datetime
from functools import lru_cache
from importlib.resources import files
import json
import re

from .core.difficulty import LEARNER_RANK
from .core.items import ItemCategory
from .core.language import LEVEL_RANK, LanguageToolkit
from .core.learner import ProfileRecord
from .core.priority import Candidate, RankedTarget, rank_targets
from .core.progress import ProgressRecord
from .features.lessons import canonical_item_id


@lru_cache(maxsize=1)
def _pack_data() -> dict:
    path = files("japanese_workplace_tutor.resources").joinpath(
        "domain_packs_v1.json")
    return json.loads(path.read_text(encoding="utf-8"))


class DomainWordService:
    def __init__(self, toolkit: LanguageToolkit) -> None:
        self._toolkit = toolkit
        self._packs = tuple(_pack_data()["packs"])

    def validate_references(self) -> tuple[str, ...]:
        missing = []
        for pack in self._packs:
            for expression in pack["words"]:
                entry = self._toolkit.lookup(expression)
                if entry is None or not entry.business_group:
                    missing.append(f"{pack['id']}: {expression}")
        return tuple(missing)

    def pack_ids_for(self, profile: ProfileRecord) -> tuple[str, ...]:
        role = profile.role.casefold()
        domain = (profile.tools_domain or "").casefold()
        def matches(text: str, keywords: list[str]) -> bool:
            return any(re.search(r"\b" + re.escape(key) + r"\b", text)
                       for key in keywords)
        matched = tuple(pack["id"] for pack in self._packs[1:]
                        if matches(role, pack["roles"])
                        or matches(domain, pack["domains"]))
        return matched or ("general-office",)

    def route_targets(
        self, expressions: tuple[str, ...], profile: ProfileRecord,
        progress: tuple[ProgressRecord, ...], now: datetime,
    ) -> tuple[RankedTarget, ...]:
        """Only reference-backed, level-appropriate words can enter a word route."""
        learner_rank = LEARNER_RANK[profile.estimated_working_level or profile.declared_level]
        by_id = {row.item_id: row for row in progress}
        candidates = []
        for expression in dict.fromkeys(expressions):
            entry = self._toolkit.lookup(expression)
            if (entry is None or not entry.business_group or not entry.level
                    or LEVEL_RANK[entry.level] > learner_rank + 1):
                continue
            item_id = canonical_item_id(ItemCategory.VOCABULARY, expression, self._toolkit)
            history = by_id.get(item_id)
            candidates.append(Candidate(
                item_id, expression, 0.0, 1.0, 0.0, 0.5, "A",
                history.mastery_score if history else 0.0, True,
                bool(history and history.next_review_at and history.next_review_at <= now),
            ))
        return rank_targets(tuple(candidates), limit=2, due_limit=1)

    def lesson_targets(
        self, scenario: str, profile: ProfileRecord,
        progress: tuple[ProgressRecord, ...], now: datetime,
    ) -> tuple[RankedTarget, ...]:
        # An explicit topic may be personal or unusual; leave it to the model
        # unless the separate situation map recognizes it.
        if scenario.strip():
            return ()
        selected_packs = set(self.pack_ids_for(profile))
        words = tuple(dict.fromkeys(
            expression for pack in self._packs if pack["id"] in selected_packs
            for expression in pack["words"]
        ))
        by_id = {row.item_id: row for row in progress}
        learner_rank = LEARNER_RANK[profile.estimated_working_level or profile.declared_level]
        candidates = []
        for expression in words:
            entry = self._toolkit.lookup(expression)
            if entry is None or not entry.business_group:
                continue
            item_id = canonical_item_id(ItemCategory.VOCABULARY, expression, self._toolkit)
            history = by_id.get(item_id)
            due = bool(history and history.next_review_at and history.next_review_at <= now)
            if history and history.mastery_score >= 0.8 and not due:
                continue
            candidates.append(Candidate(
                item_id, expression, 1.0 if selected_packs != {"general-office"} else 0.0,
                0.0, 0.0, 0.5, "A", history.mastery_score if history else 0.0,
                bool(entry.level and LEVEL_RANK[entry.level] <= learner_rank + 1), due,
            ))
        for history in progress:
            if (history.category is not ItemCategory.VOCABULARY or not history.expression
                    or not history.next_review_at or history.next_review_at > now):
                continue
            entry = self._toolkit.lookup(history.expression)
            if entry is None or not entry.business_group:
                continue
            candidates.append(Candidate(
                history.item_id, history.expression, 0.0, 0.0, 0.0, 0.5, "A",
                history.mastery_score,
                bool(entry.level and LEVEL_RANK[entry.level] <= learner_rank + 1), True,
            ))
        ranked = rank_targets(tuple(candidates), limit=len(candidates), due_limit=1)
        exposure = {row.item_id: row.exposure_count for row in progress}
        due_ids = {row.item_id for row in candidates if row.due}
        return tuple(sorted(ranked, key=lambda row: (
            row.item_id not in due_ids, exposure.get(row.item_id, 0), -row.priority,
            row.item_id,
        ))[:2])
