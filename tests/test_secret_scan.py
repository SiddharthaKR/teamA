import os
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".ini", ".ipynb", ".md", ".py", ".toml", ".txt", ".yaml", ".yml", ".example"}
SECRET_PATTERNS = {
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "assigned credential": re.compile(
        r"(?i)(api[_-]?key|virtual[_-]?key|token|password)\s*=\s*[\"'][A-Za-z0-9_./+-]{16,}[\"']"
    ),
}


IGNORED_DIRS = {".git", ".pytest_cache", ".venv", "__pycache__", "data", "node_modules"}


def tracked_text_files() -> list[Path]:
    # Prune ignored directories while walking: rglob would still descend into
    # .venv, which takes minutes on slow or network-mounted file systems.
    files: list[Path] = []
    for directory, subdirectories, names in os.walk(PROJECT_ROOT):
        subdirectories[:] = [name for name in subdirectories if name not in IGNORED_DIRS]
        for name in names:
            path = Path(directory) / name
            if path.suffix in TEXT_SUFFIXES or name == ".env.example":
                files.append(path)
    return files


def test_repository_contains_no_secret_patterns() -> None:
    findings: list[str] = []
    for path in tracked_text_files():
        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern_name, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{path.relative_to(PROJECT_ROOT)}: {pattern_name}")

    assert not findings, "Potential credentials found:\n" + "\n".join(findings)
