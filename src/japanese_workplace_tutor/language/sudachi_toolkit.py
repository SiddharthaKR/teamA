"""LanguageToolkit adapter: SudachiPy tokenization + JLPT reference lists + curated lists.

Reference data, in priority order (later sources win):
1. OpenJLPT 0.1.0 fills words the primary list lacks. It is an alpha dataset with
   known level and reading errors, so it is only a fallback.
2. tanos-v1 (resources/jlpt_vocab_tanos_v1.json) is the primary JLPT list:
   Jonathan Waller's tanos.co.uk lists (CC BY) as maintained in
   jamsinclair/open-anki-jlpt-decks (MIT).
3. override-v1 corrects known errors in both.
4. business-v1 tags curated workplace words; it keeps a word's JLPT level and adds
   words no JLPT list has (共有, 進捗, メール).
When a list has a word at several levels, the easiest level wins. Every entry
carries its provenance, and the team accuracy review checks them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from functools import lru_cache
from importlib import resources
import json
import re
from threading import Lock

from ..core.japanese import is_kana_only
from ..core.language import LEVEL_RANK, GrammarPoint, LexiconEntry, Token, WordSet, to_hiragana

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
        self.version = (
            f"sudachi-core+tanos-v1+openjlpt-{openjlpt.__version__}"
            "+override-v1+business-v1+grammar-list-v1"
        )
        self._lexicon = self._build_lexicon(openjlpt)
        self._grammar = self._load_grammar()
        self._word_sets = self._build_word_sets()

    @classmethod
    @lru_cache(maxsize=1)
    def shared(cls) -> "SudachiToolkit":
        return cls()

    # -- reference data -------------------------------------------------
    @staticmethod
    def _resource(name: str) -> dict:
        return json.loads(
            resources.files("japanese_workplace_tutor.resources").joinpath(name).read_text(encoding="utf-8")
        )

    @staticmethod
    def _merge_list(rows, provenance: str) -> dict[str, LexiconEntry]:
        """rows: (word, raw reading, level, meanings). Easiest level wins per word."""

        levels: dict[str, list[str]] = defaultdict(list)
        readings: dict[str, set[str]] = defaultdict(set)
        meanings: dict[str, list[str]] = defaultdict(list)
        for word, reading, level, word_meanings in rows:
            levels[word].append(level)
            cleaned = _clean_readings(word, reading)
            if cleaned:
                readings[word].update(cleaned)
            elif is_kana_only(word):
                readings[word].add(to_hiragana(word))
            meanings[word].extend(m for m in word_meanings if m not in meanings[word])
        return {
            word: LexiconEntry(
                lemma=word,
                readings=frozenset(readings[word]),
                level=min(word_levels, key=LEVEL_RANK.__getitem__),
                meanings=tuple(meanings[word]),
                provenance=provenance,
            )
            for word, word_levels in levels.items()
        }

    @classmethod
    def _build_lexicon(cls, openjlpt) -> dict[str, LexiconEntry]:
        lexicon = cls._merge_list(
            (
                (vocab.word, vocab.reading, vocab.level, vocab.meanings)
                for level in openjlpt.levels
                for vocab in openjlpt.get_vocab(level)
            ),
            f"openjlpt-{openjlpt.__version__}",
        )
        tanos = cls._resource("jlpt_vocab_tanos_v1.json")
        lexicon.update(
            cls._merge_list(
                (
                    (word, reading, level, tuple(m.strip() for m in meaning.split(",") if m.strip()))
                    for word, reading, level, meaning in tanos["entries"]
                ),
                tanos["version"],
            )
        )
        overrides = cls._resource("jlpt_overrides_v1.json")
        for entry in overrides["entries"]:
            lexicon[entry["lemma"]] = LexiconEntry(
                lemma=entry["lemma"],
                readings=frozenset(entry["readings"]),
                level=entry["level"],
                meanings=tuple(entry["meanings"]),
                provenance=overrides["version"],
            )
        business = cls._resource("business_vocab_v1.json")
        for raw in business["entries"]:
            known = lexicon.get(raw["lemma"])
            if known is not None:
                entry = replace(
                    known,
                    readings=known.readings | frozenset(raw["readings"]),
                    business_group=raw["group"],
                )
            else:
                entry = LexiconEntry(
                    lemma=raw["lemma"],
                    readings=frozenset(raw["readings"]),
                    level=None,
                    meanings=tuple(raw["meanings"]),
                    provenance=business["version"],
                    business_group=raw["group"],
                )
            lexicon[raw["lemma"]] = entry
            for alternate in raw.get("alternates", ()):
                # Alternate spellings share the canonical entry, so they share one item.
                lexicon[alternate] = entry
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
            return self._lexicon[text].lemma
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

    def grammar_by_id(self, point_id: str) -> GrammarPoint | None:
        return self._grammar_ids.get(point_id)

    def word_sets(self) -> tuple[WordSet, ...]:
        return self._word_sets

    def entries_at(self, level: str) -> tuple[LexiconEntry, ...]:
        return self._by_level.get(level, ())

    def _build_word_sets(self) -> tuple[WordSet, ...]:
        entries = {entry.lemma: entry for entry in self._lexicon.values()}
        by_level: dict[str, list[LexiconEntry]] = defaultdict(list)
        by_group: dict[str, set[str]] = defaultdict(set)
        for lemma in sorted(entries):
            entry = entries[lemma]
            # Level sets come from the primary list and fixes, not the OpenJLPT gap
            # fill, so coverage is measured against one reviewed list.
            if entry.level and not entry.provenance.startswith("openjlpt"):
                by_level[entry.level].append(entry)
            if entry.business_group:
                by_group[entry.business_group].add(lemma)
        self._by_level = {level: tuple(items) for level, items in by_level.items()}
        self._grammar_ids = {point.id: point for point in self._grammar.values()}
        grammar_by_level: dict[str, set[str]] = defaultdict(set)
        for point in self._grammar_ids.values():
            if point.level:
                grammar_by_level[point.level].add(point.id)
        group_labels = self._resource("business_vocab_v1.json")["groups"]
        sets = []
        for level in ("N5", "N4", "N3", "N2", "N1"):
            sets.append(
                WordSet(
                    f"jlpt-{level}",
                    f"JLPT {level} words",
                    "words",
                    frozenset(entry.lemma for entry in by_level.get(level, ())),
                )
            )
            if grammar_by_level.get(level):
                sets.append(
                    WordSet(
                        f"grammar-{level}",
                        f"JLPT {level} grammar",
                        "grammar",
                        frozenset(grammar_by_level[level]),
                    )
                )
        for group, label in group_labels.items():
            sets.append(
                WordSet(f"business-{group}", f"Business: {label}", "words", frozenset(by_group[group]))
            )
        return tuple(sets)
