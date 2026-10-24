"""Compute error rates from a review sheet the team filled in.

    python scripts/score_review_sheet.py data/review-sheets/review_sheet.csv --target 0.02

Counts rows whose "Correct? (Y/N)" is Y or N; blank rows are not reviewed.
Exits with status 1 when graded answer keys miss the target error rate.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from pathlib import Path

COLUMN = "Correct? (Y/N)"


def score(path: Path) -> dict[str, tuple[int, int]]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            mark = (row.get(COLUMN) or "").strip().upper()[:1]
            if mark not in ("Y", "N"):
                continue
            groups = ["all", row["kind"]]
            if row["kind"] == "question":
                groups.append(f"question:{row.get('key_source') or 'unknown'}")
            for group in groups:
                totals[group][0] += mark == "N"
                totals[group][1] += 1
    return {group: (wrong, total) for group, (wrong, total) in totals.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--target", type=float, default=None, help="max error rate for graded keys")
    args = parser.parse_args()
    results = score(args.sheet)
    for group, (wrong, total) in sorted(results.items()):
        print(f"{group:28s} {wrong:4d} wrong / {total:4d} reviewed = {wrong / total:6.1%}")
    graded = [results[g] for g in ("question:derived", "question:curated") if g in results]
    if args.target is not None and graded:
        wrong = sum(w for w, _ in graded)
        total = sum(t for _, t in graded)
        rate = wrong / total
        print(f"\nGraded answer keys: {rate:.1%} (target {args.target:.1%})")
        raise SystemExit(0 if rate <= args.target else 1)


if __name__ == "__main__":
    main()
