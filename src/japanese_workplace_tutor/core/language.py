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
    provenance: str  # e.g. "tanos-v1", "openjlpt-0.1.0", "override-v1", "business-v1"
    business_group: str | None = None  # set when the word is on the curated workplace list


@dataclass(frozen=True)
class GrammarPoint:
    id: str
    display: str
    forms: tuple[str, ...]
    level: JLPTLevel | None
    meanings: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class WordSet:
    """A named reference set a learner's coverage is measured against.

    Members are lemmas for word sets and grammar point ids for grammar sets.
    """

    id: str  # e.g. "jlpt-N4", "grammar-N4", "business-meetings"
    label: str
    kind: Literal["words", "grammar"]
    members: frozenset[str]


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

    def grammar_by_id(self, point_id: str) -> GrammarPoint | None: ...

    def word_sets(self) -> tuple[WordSet, ...]:
        """JLPT word sets by level, grammar sets by level, Business Japanese groups."""
        ...

    def entries_at(self, level: str) -> tuple[LexiconEntry, ...]:
        """Lexicon entries rated at one JLPT level, one per lemma, in a stable order."""
        ...


BUSINESS_LABEL = "Business Japanese"


def jlpt_label(level: str | None) -> str | None:
    return f"JLPT {level}" if level else None


def reference_label(entry: LexiconEntry) -> str | None:
    """JLPT level when the reference lists rate the word; else the workplace section."""

    if entry.level:
        return jlpt_label(entry.level)
    return BUSINESS_LABEL if entry.business_group else None


def to_hiragana(text: str) -> str:
    return "".join(
        chr(ord(character) - 0x60) if "ァ" <= character <= "ヶ" else character
        for character in text
    )
