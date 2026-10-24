"""The language toolkit port: Japanese facts come from here, never from the model.

The core defines the shapes and the interface; an adapter (language/) fills it
from a tokenizer and curated reference data. Nothing here does IO.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

JLPTLevel = Literal["N5", "N4", "N3", "N2", "N1"]
LEVEL_RANK: dict[str, int] = {"N5": 1, "N4": 2, "N3": 3, "N2": 4, "N1": 5}


@dataclass(frozen=True)
class Token:
    surface: str
    lemma: str
    reading: str  # hiragana
    pos: tuple[str, ...]
    is_content: bool  # nouns, verbs, adjectives, adverbs; not particles or auxiliaries


@dataclass(frozen=True)
class LexiconEntry:
    lemma: str
    readings: frozenset[str]  # every reading the reference data accepts, in hiragana
    level: JLPTLevel | None
    meanings: tuple[str, ...]
    provenance: str  # e.g. "openjlpt-0.1.0", "override-v1"


@dataclass(frozen=True)
class GrammarPoint:
    id: str
    display: str
    forms: tuple[str, ...]
    level: JLPTLevel | None
    meanings: tuple[str, ...]
    provenance: str


class LanguageToolkit(Protocol):
    version: str

    def tokenize(self, text: str) -> tuple[Token, ...]: ...

    def lemma(self, expression: str) -> str:
        """Dictionary form of a single-word expression; the expression itself otherwise."""
        ...

    def lookup(self, expression: str) -> LexiconEntry | None: ...

    def readings(self, expression: str) -> frozenset[str]:
        """All acceptable hiragana readings: tokenizer reading plus reference readings."""
        ...

    def grammar_point(self, expression: str) -> GrammarPoint | None: ...


def jlpt_label(level: str | None) -> str | None:
    return f"JLPT {level}" if level else None


def to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(character) - 0x60) if "ァ" <= character <= "ヶ" else character
        for character in text
    )
