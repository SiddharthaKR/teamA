"""Decide which answer keys code can vouch for (Trust Tier 1).

A generated question is graded only when its key can be confirmed against the
lesson passage or the reference data, and no distractor could also be right.
Anything else stays in the lesson as practice and never changes progress.
"""

from collections.abc import Iterable, Sequence
import re

from .items import FixtureItem, FixtureQuestion, ItemCategory, KeySource, LessonContent, QuestionForm
from .language import LanguageToolkit, to_hiragana

BLANK = re.compile(r"_{2,}|＿+|\(\s*\)|（\s*）")
STOPWORDS = {
    "a", "an", "the", "to", "of", "for", "be", "is", "are", "do", "it", "in", "on", "at",
    "and", "or", "someone", "something", "one", "s", "with", "that", "this", "as",
}


def _stems(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {word[:5] for word in words if word not in STOPWORDS}


def _overlaps(text: str, glosses: Iterable[str]) -> bool:
    stems = _stems(text)
    return any(stems & _stems(gloss) for gloss in glosses)


def _compact(text: str) -> str:
    return re.sub(r"[\s　「」『』]", "", text)


def _glosses(item: FixtureItem, toolkit: LanguageToolkit) -> tuple[str, ...]:
    if item.category is ItemCategory.GRAMMAR:
        point = toolkit.grammar_point(item.expression)
        return point.meanings if point else ()
    entry = toolkit.lookup(item.expression)
    return entry.meanings if entry else ()


def _cloze_segment(prompt: str) -> str | None:
    match = BLANK.search(prompt)
    if match is None:
        return None
    start = max(prompt.rfind(":", 0, match.start()), prompt.rfind("：", 0, match.start())) + 1
    return prompt[start:].strip()


def _item_forms(item: FixtureItem, toolkit: LanguageToolkit) -> tuple[str, ...]:
    expression = re.sub(r"[〜～~\s]", "", item.expression)
    if item.category is ItemCategory.GRAMMAR:
        point = toolkit.grammar_point(item.expression)
        return (expression, *(point.forms if point else ()))
    return (expression, toolkit.lemma(item.expression))


def verify_question(
    question: FixtureQuestion, content: LessonContent, toolkit: LanguageToolkit
) -> KeySource:
    item = next((i for i in content.items if i.canonical_id == question.item_id), None)
    if item is None:
        return KeySource.UNVERIFIED
    key = question.options[question.correct_option_index]
    distractors = [o for i, o in enumerate(question.options) if i != question.correct_option_index]

    if question.form is QuestionForm.READING:
        accepted = {to_hiragana(r) for r in toolkit.readings(item.expression)}
        if accepted and to_hiragana(key.strip()) in accepted and not any(
            to_hiragana(d.strip()) in accepted for d in distractors
        ):
            return KeySource.DERIVED
        return KeySource.UNVERIFIED

    if question.form is QuestionForm.MEANING:
        glosses = _glosses(item, toolkit)
        if glosses and _overlaps(key, glosses) and not any(_overlaps(d, glosses) for d in distractors):
            return KeySource.DERIVED
        return KeySource.UNVERIFIED

    if question.form is QuestionForm.CONTEXTUAL_CLOZE:
        segment = _cloze_segment(question.prompt)
        if segment is None:
            return KeySource.UNVERIFIED
        passage = _compact(content.passage)

        def appears(option: str) -> bool:
            return _compact(BLANK.sub(option.strip(), segment, count=1)) in passage

        # The blank must hide the target item itself, not some other word.
        tests_item = any(form and form in key for form in _item_forms(item, toolkit))
        if appears(key) and tests_item and not any(
            appears(d) for d in distractors
        ):
            return KeySource.DERIVED
        return KeySource.UNVERIFIED

    # Register and nuance questions need human judgment (decision 3).
    return KeySource.UNVERIFIED


def verify_questions(
    questions: Sequence[FixtureQuestion], content: LessonContent, toolkit: LanguageToolkit
) -> tuple[FixtureQuestion, ...]:
    return tuple(
        question.model_copy(update={"key_source": verify_question(question, content, toolkit)})
        for question in questions
    )
