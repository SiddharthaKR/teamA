"""Architecture gates: import contracts and request shaping rules."""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from japanese_workplace_tutor.core.inputs import expected_line_count
from japanese_workplace_tutor.profile import JapaneseLevel

from test_generation import profile

ROOT = Path(__file__).resolve().parents[1]


def test_import_contracts_hold() -> None:
    lint_imports = shutil.which("lint-imports") or str(Path(sys.executable).parent / "lint-imports")
    if not Path(lint_imports).exists():
        pytest.skip("import-linter is not installed (pip install -r requirements-dev.txt)")
    result = subprocess.run(
        [lint_imports, "--no-cache"], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("level", "lines"),
    [
        (JapaneseLevel.COMPLETE_BEGINNER, 6),
        (JapaneseLevel.N5, 6),
        (JapaneseLevel.N4, 8),
        (JapaneseLevel.UNSURE, 8),
        (JapaneseLevel.N3, 10),
        (JapaneseLevel.N2, 10),
        (JapaneseLevel.N1, 10),
    ],
)
def test_dialogue_length_never_gives_beginners_the_longest_lesson(level, lines) -> None:
    assert expected_line_count(profile(level)) == lines
