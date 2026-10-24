"""Build resources/jlpt_vocab_tanos_v1.json from the open-anki-jlpt-decks CSVs.

Usage: python scripts/build_jlpt_resource.py <dir with n1.csv .. n5.csv>

Source: https://github.com/jamsinclair/open-anki-jlpt-decks (MIT), whose notes
come from Jonathan Waller's JLPT lists at tanos.co.uk (CC BY). The rows are
copied as published; cleaning (split readings, stray する) happens at load time
in the toolkit, so one code path handles every source. Standard library only.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parents[1] / "src" / "japanese_workplace_tutor" / "resources" / "jlpt_vocab_tanos_v1.json"


def find(directory: Path, level: int) -> Path:
    for name in (f"n{level}.csv", f"jams_n{level}.csv"):
        if (directory / name).exists():
            return directory / name
    raise SystemExit(f"missing n{level}.csv in {directory}")


def main(directory: Path) -> None:
    rows = []
    for level in (5, 4, 3, 2, 1):
        with find(directory, level).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                word = row["expression"].strip()
                if word:
                    rows.append([word, row["reading"].strip(), f"N{level}", row["meaning"].strip()])
    payload = {
        "version": "tanos-v1",
        "source": "jamsinclair/open-anki-jlpt-decks (MIT) from tanos.co.uk JLPT lists by Jonathan Waller (CC BY)",
        "fields": ["word", "reading", "level", "meaning"],
        "entries": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
