"""Deterministic lesson target ranking; due reviews form a separate lane."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    item_id: str
    expression: str
    domain_match: float
    situation_match: float
    partner_match: float
    frequency: float
    importance: str
    mastery: float
    eligible: bool
    due: bool


@dataclass(frozen=True)
class RankedTarget:
    item_id: str
    expression: str
    priority: float
    reason: str


def rank_targets(
    candidates: tuple[Candidate, ...], *, limit: int = 7, due_limit: int = 2
) -> tuple[RankedTarget, ...]:
    """Pick eligible targets; a due item can recur even at full mastery."""
    weights = {"S": 3, "A": 2, "B": 1}
    scored = []
    for candidate in candidates:
        if not candidate.eligible or candidate.importance not in weights:
            continue
        score = (
            0.4 * candidate.domain_match
            + 0.3 * candidate.situation_match
            + 0.2 * candidate.partner_match
            + 0.1 * candidate.frequency
        ) * weights[candidate.importance] * (1 - candidate.mastery)
        reason = (
            "due for review" if candidate.due else
            "personal priority" if candidate.importance == "S" else
            "matches your work" if candidate.domain_match > 0 else
            "common workplace word"
        )
        scored.append((candidate, score, reason))

    unique = {}
    for row in scored:
        item_id = row[0].item_id
        previous = unique.get(item_id)
        if previous is None or (row[0].due, row[1]) > (previous[0].due, previous[1]):
            unique[item_id] = row

    due = sorted((row for row in unique.values() if row[0].due),
                 key=lambda row: (-row[1], row[0].item_id))[:max(0, due_limit)]
    selected_ids = {row[0].item_id for row in due}
    rest = sorted((row for row in unique.values() if row[0].item_id not in selected_ids),
                  key=lambda row: (-row[1], row[0].item_id))
    selected = (due + rest)[:max(0, limit)]
    return tuple(RankedTarget(row.item_id, row.expression, score, reason)
                 for row, score, reason in selected)
