"""Review questions built by code from reference data, for items from generated lessons.

An item learned in a generated lesson has no stored question, so it could not be
reviewed when due. These questions are built only from the reference lists (the
expression, its readings and meanings), never by the model, so the answer key is
code-verified (KeySource.DERIVED) and the answer is graded.
"""

from collections.abc import Mapping, Sequence
from hashlib import sha256
from random import Random
import re

from ..core.items import FixtureItem, FixtureQuestion, ItemCategory, KeySource, QuestionForm
from ..core.japanese import contains_kanji, is_kana_only
from ..core.language import LEVEL_RANK, LanguageToolkit, jlpt_label, reference_label
from ..core.progress import skill_dimension

_STOP = {
    "a", "an", "the", "to", "be", "of", "in", "on", "at", "for", "with", "and", "or",
    "one", "one's", "something", "someone", "somebody", "etc", "is", "it", "by", "as",
}
_VOICING = dict(
    pair
    for a, b in zip("かきくけこさしすせそたちつてとはひふへほ", "がぎぐげござじずぜぞだぢづでどばびぶべぼ")
    for pair in ((a, b), (b, a))
)
_O_ROW = set("おこごそぞとどのほぼぽもよょろ")
_GEMINATE_BEFORE = set("かきくけこさしすせそたちつてとぱぴぷぺぽ")
MAX_OPTION_LENGTH = 48


def _words(meaning: str) -> set[str]:
    return {word for word in re.findall(r"[a-z']+", meaning.lower()) if word not in _STOP}


def _overlaps(candidate: str, meanings: Sequence[str]) -> bool:
    words = _words(candidate)
    return any(words & _words(meaning) for meaning in meanings) or candidate in meanings


def _seed(*parts: str) -> Random:
    return Random(int(sha256("|".join(parts).encode("utf-8")).hexdigest()[:16], 16))


def _reading_mutations(reading: str) -> list[str]:
    """Plausible wrong readings: voicing, long vowels, small っ (distractor by mutation)."""

    found = []
    for index, character in enumerate(reading):
        if character in _VOICING:
            found.append(reading[:index] + _VOICING[character] + reading[index + 1 :])
        if character in _O_ROW:
            following = reading[index + 1 : index + 2]
            if following == "う":
                found.append(reading[: index + 1] + reading[index + 2 :])
            else:
                found.append(reading[: index + 1] + "う" + reading[index + 1 :])
        if character == "っ":
            found.append(reading[:index] + reading[index + 1 :])
        elif character in _GEMINATE_BEFORE and index > 0 and reading[index - 1] != "っ":
            found.append(reading[:index] + "っ" + reading[index:])
    return found


def _pick(pool: Sequence[str], rng: Random, count: int, reject) -> list[str] | None:
    candidates = list(dict.fromkeys(pool))
    rng.shuffle(candidates)
    chosen: list[str] = []
    for candidate in candidates:
        if candidate and len(candidate) <= MAX_OPTION_LENGTH and not reject(candidate) and candidate not in chosen:
            chosen.append(candidate)
            if len(chosen) == count:
                return chosen
    return None


def _pick_ordered(pool: Sequence[str], count: int, reject) -> list[str] | None:
    chosen: list[str] = []
    for candidate in pool:
        if candidate and not reject(candidate) and candidate not in chosen:
            chosen.append(candidate)
            if len(chosen) == count:
                return chosen
    return None


def _question(item_id: str, form: QuestionForm, prompt: str, correct: str, distractors: list[str], explanation: str) -> FixtureQuestion:
    digest = sha256(f"{item_id}|{form.value}".encode("utf-8")).hexdigest()[:16]
    return FixtureQuestion(
        question_id=f"rv-{form.value}-{digest}",
        item_id=item_id,
        form=form,
        prompt=prompt,
        options=(correct, *distractors),
        correct_option_index=0,
        explanation=explanation,
        key_source=KeySource.DERIVED,
    )


def _nearby_levels(level: str | None) -> list[str]:
    rank = LEVEL_RANK.get(level or "N5", 1)
    return sorted(LEVEL_RANK, key=lambda name: (abs(LEVEL_RANK[name] - rank), LEVEL_RANK[name]))


def _grammar_review(item_id: str, expression: str, toolkit: LanguageToolkit):
    point = None
    if item_id.startswith("grammar:"):
        point = toolkit.grammar_by_id(item_id.split(":", 1)[1])
    point = point or toolkit.grammar_point(expression)
    if point is None or not point.meanings:
        return None
    others = [
        other
        for set_ in toolkit.word_sets()
        if set_.kind == "grammar"
        for other_id in sorted(set_.members)
        if other_id != point.id and (other := toolkit.grammar_by_id(other_id)) is not None
    ]
    rank = LEVEL_RANK.get(point.level or "N5", 1)
    others.sort(key=lambda other: (abs(LEVEL_RANK.get(other.level or "N5", 1) - rank), other.id))
    pool = [other.meanings[0] for other in others[:24] if other.meanings]
    distractors = _pick(pool, _seed(item_id, "meaning"), 3, lambda c: _overlaps(c, point.meanings))
    if distractors is None:
        return None
    item = FixtureItem(
        canonical_id=item_id,
        category=ItemCategory.GRAMMAR,
        expression=point.display,
        reading=point.forms[0] if point.forms else point.display,
        meaning="; ".join(point.meanings),
        example=f"{point.display}: {point.meanings[0]}",
        jlpt_level=jlpt_label(point.level),
        jlpt_provenance=point.provenance,
        jlpt_confidence=0.8,
    )
    question = _question(
        item_id,
        QuestionForm.MEANING,
        f"What does 「{point.display}」 express?",
        point.meanings[0],
        distractors,
        f"「{point.display}」 expresses: {'; '.join(point.meanings)}. Source: {point.provenance}.",
    )
    return item, (question,)


def _word_review(item_id: str, category: ItemCategory, expression: str, toolkit: LanguageToolkit):
    entry = toolkit.lookup(expression)
    if entry is None or not entry.meanings:
        return None
    accepted = set(entry.readings) | set(toolkit.readings(entry.lemma))
    preferred = sorted(set(entry.readings) & set(toolkit.readings(entry.lemma))) or sorted(entry.readings)
    reading = preferred[0] if preferred else None
    if reading is None:
        return None
    meaning_text = "; ".join(entry.meanings[:3])
    item = FixtureItem(
        canonical_id=item_id,
        category=category,
        expression=entry.lemma,
        reading=reading,
        meaning=meaning_text,
        example=f"{entry.lemma}（{reading}）",
        jlpt_level=reference_label(entry),
        jlpt_provenance=entry.provenance,
        jlpt_confidence=0.8,
    )
    explanation = f"「{entry.lemma}」 is read {reading} and means “{meaning_text}”. Source: {entry.provenance}."
    questions = []
    pool = [
        other.meanings[0]
        for level in _nearby_levels(entry.level)[:2]
        for other in toolkit.entries_at(level)
        if other.lemma != entry.lemma and other.meanings
    ]
    distractors = _pick(pool, _seed(item_id, "meaning"), 3, lambda c: _overlaps(c, entry.meanings))
    if distractors is not None:
        questions.append(
            _question(item_id, QuestionForm.MEANING, f"What does 「{entry.lemma}」 mean?", entry.meanings[0], distractors, explanation)
        )
    if contains_kanji(entry.lemma):
        reject = lambda c: c in accepted or not is_kana_only(c)  # noqa: E731
        mutations = _reading_mutations(reading)
        _seed(item_id, "reading").shuffle(mutations)
        similar = sorted(
            {
                other_reading
                for other in toolkit.entries_at(entry.level or "N5")
                for other_reading in other.readings
                if abs(len(other_reading) - len(reading)) <= 1
            },
            key=lambda other_reading: (other_reading[:1] != reading[:1], other_reading),
        )[:12]
        _seed(item_id, "reading-pool").shuffle(similar)
        distractors = _pick_ordered([*mutations, *similar], 3, reject)
        if distractors is not None:
            questions.append(
                _question(item_id, QuestionForm.READING, f"How is 「{entry.lemma}」 read?", reading, distractors, explanation)
            )
    if not questions:
        return None
    return item, tuple(questions)


def build_review(
    item_id: str,
    category: ItemCategory,
    expression: str,
    dimension_scores: Mapping[str, float],
    toolkit: LanguageToolkit,
) -> tuple[FixtureItem, FixtureQuestion] | None:
    """The item and its review question, aimed at the weakest skill; None if not buildable."""

    if category is ItemCategory.GRAMMAR:
        built = _grammar_review(item_id, expression, toolkit)
    else:
        built = _word_review(item_id, category, expression, toolkit)
    if built is None:
        return None
    item, questions = built
    question = min(
        questions,
        key=lambda candidate: (
            dimension_scores.get(skill_dimension(candidate.form, category).value, 0.0),
            candidate.question_id,
        ),
    )
    return item, question
