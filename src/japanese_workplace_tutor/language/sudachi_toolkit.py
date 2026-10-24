"""LanguageToolkit adapter: SudachiPy tokenization + OpenJLPT levels + curated lists.

Reference data quality: OpenJLPT 0.1.0 is an alpha dataset with known errors
(some levels and readings are wrong). Levels are therefore treated as reference
data with provenance, corrected by resources/jlpt_overrides_v1.json, and checked
by the team accuracy review. When a word has entries at several levels, the
easiest level wins.
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from importlib import resources
import json
import re
from threading import Lock

from ..core.japanese import is_kana_only
from ..core.language import LEVEL_RANK, GrammarPoint, LexiconEntry, Token, to_hiragana

NON_CONTENT_POS = {"助詞", "助動詞", "補助記号", "記号", "空白", "接尾辞"}
LIGHT_VERBS = {"する", "為る", "ある", "有る", "いる", "居る", "なる", "成る"}
_STRIP = re.compile(r"[〜～~\s　]|（[^）]*）|\([^)]*\)")


def normalize_expression(expression: str) -> str:
    return _STRIP.sub("", expression).strip()


def _clean_readings(word: str, reading: str) -> set[str]:
    """Split "なん/なに", drop a stray する suffix and anything that is not kana."""

    cleaned = set()
    for part in re.split(r"[/／・,、]", reading):
        part = to_hiragana(part.strip())
        if part.endswith("する") and not word.endswith("する") and len(part) > 2:
            part = part[:-2]
        if part and is_kana_only(part):
            cleaned.add(part)
    return cleaned


class SudachiToolkit:
    """Deterministic, offline language facts. Thread-safe; build once and share."""

    def __init__(self) -> None:
        from sudachipy import Dictionary, SplitMode
        import openjlpt

        self._split_mode = SplitMode.C
        self._tokenizer = Dictionary(dict="core").tokenizer()
        self._lock = Lock()
        self.version = f"sudachi-core+openjlpt-{openjlpt.__version__}+override-v1+grammar-list-v1"
        self._lexicon = self._build_lexicon(openjlpt)
        self._grammar = self._load_grammar()

    @classmethod
    @lru_cache(maxsize=1)
    def shared(cls) -> "SudachiToolkit":
        return cls()

    # -- reference data -------------------------------------------------
    @staticmethod
    def _build_lexicon(openjlpt) -> dict[str, LexiconEntry]:
        levels: dict[str, list[str]] = defaultdict(list)
        readings: dict[str, set[str]] = defaultdict(set)
        meanings: dict[str, list[str]] = defaultdict(list)
        for level in openjlpt.levels:
            for vocab in openjlpt.get_vocab(level):
                levels[vocab.word].append(vocab.level)
                cleaned = _clean_readings(vocab.word, vocab.reading)
                if cleaned:
                    readings[vocab.word].update(cleaned)
                elif is_kana_only(vocab.word):
                    readings[vocab.word].add(to_hiragana(vocab.word))
                meanings[vocab.word].extend(m for m in vocab.meanings if m not in meanings[vocab.word])
        provenance = f"openjlpt-{openjlpt.__version__}"
        lexicon = {
            word: LexiconEntry(
                lemma=word,
                readings=frozenset(readings[word]),
                level=min(word_levels, key=LEVEL_RANK.__getitem__),
                meanings=tuple(meanings[word]),
                provenance=provenance,
            )
            for word, word_levels in levels.items()
        }
        overrides = json.loads(
            resources.files("japanese_workplace_tutor.resources")
            .joinpath("jlpt_overrides_v1.json")
            .read_text(encoding="utf-8")
        )
        for entry in overrides["entries"]:
            lexicon[entry["lemma"]] = LexiconEntry(
                lemma=entry["lemma"],
                readings=frozenset(entry["readings"]),
                level=entry["level"],
                meanings=tuple(entry["meanings"]),
                provenance=overrides["version"],
            )
        return lexicon

    @staticmethod
    def _load_grammar() -> dict[str, GrammarPoint]:
        data = json.loads(
            resources.files("japanese_workplace_tutor.resources")
            .joinpath("grammar_points_v1.json")
            .read_text(encoding="utf-8")
        )
        by_form: dict[str, GrammarPoint] = {}
        for raw in data["points"]:
            point = GrammarPoint(
                id=raw["id"],
                display=raw["display"],
                forms=tuple(raw["forms"]),
                level=raw["level"],
                meanings=tuple(raw["meanings"]),
                provenance=data["version"],
            )
            for form in (*point.forms, normalize_expression(point.display)):
                by_form.setdefault(normalize_expression(form), point)
        return by_form

    # -- LanguageToolkit -------------------------------------------------
    def tokenize(self, text: str) -> tuple[Token, ...]:
        with self._lock:
            morphemes = list(self._tokenizer.tokenize(text, self._split_mode))
        tokens = []
        for morpheme in morphemes:
            pos = tuple(part for part in morpheme.part_of_speech() if part != "*")
            lemma = morpheme.dictionary_form()
            is_content = bool(pos) and pos[0] not in NON_CONTENT_POS and not (
                lemma in LIGHT_VERBS and len(pos) > 1 and pos[1] == "非自立可能"
            )
            tokens.append(
                Token(
                    surface=morpheme.surface(),
                    lemma=lemma,
                    reading=to_hiragana(morpheme.reading_form()),
                    pos=pos,
                    is_content=is_content,
                )
            )
        return tuple(tokens)

    def lemma(self, expression: str) -> str:
        text = normalize_expression(expression)
        if text in self._lexicon:
            return text
        content = [token for token in self.tokenize(text) if token.is_content]
        if len(content) == 1:
            return content[0].lemma
        return text

    def lookup(self, expression: str) -> LexiconEntry | None:
        text = normalize_expression(expression)
        return self._lexicon.get(text) or self._lexicon.get(self.lemma(text))

    def readings(self, expression: str) -> frozenset[str]:
        text = normalize_expression(expression)
        found: set[str] = set()
        tokens = self.tokenize(text)
        if tokens and all(token.reading for token in tokens):
            found.add("".join(token.reading for token in tokens))
        entry = self._lexicon.get(text)
        if entry:
            found.update(entry.readings)
        if is_kana_only(text):
            found.add(to_hiragana(text))
        return frozenset(found)

    def grammar_point(self, expression: str) -> GrammarPoint | None:
        return self._grammar.get(normalize_expression(expression))
