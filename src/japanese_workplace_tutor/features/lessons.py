"""Lesson feature: generate content, then a quiz, and hold both to their contracts.

The model proposes dialogue, explanations and questions; this module decides
what is accepted. Target items are derived here from the explained language
points, never taken from the model as-is.
"""

from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import hashlib

from pydantic import BaseModel, ValidationError

from ..core.difficulty import DifficultyReport, measure
from ..core.errors import ContractViolation, GenerationError
from ..core.inputs import DEFAULT_LINE_COUNT, ScenarioInput, ScenarioMode, expected_line_count
from ..core.items import (
    FixtureItem,
    ItemCategory,
    LessonContent,
    LessonExplanationPoint,
    LessonLineExplanation,
    QuestionForm,
)
from ..core.language import LanguageToolkit, jlpt_label, to_hiragana
from ..core.japanese import contains_japanese, contains_kanji, is_japanese_name, is_kana_only, is_non_japanese_name
from ..core.learner import JapaneseLevel, ProfileRecord
from ..core.ports import DataClass
from ..core.progress import ProgressRecord
from ..core.verification import verify_questions
from ..llm.gateway import LLMGateway
from ..prompts import lessons as prompts
from ..schemas.lessons import (
    GeneratedConversationResponse,
    GeneratedDialogueResponse,
    GeneratedExplainHeaderResponse,
    GeneratedExplanationResponse,
    GeneratedLessonContentPackage,
    GeneratedLessonDraft,
    GeneratedLine,
    GeneratedLineExplanationResponse,
    GeneratedLanguagePoint,
    GeneratedQuiz,
    GeneratedQuizPackage,
    GeneratedTitledResponse,
)


def _dialogue_text(value: str) -> str:
    """Return the spoken Japanese, dropping a speaker label the model may have added."""

    text = value.strip()
    for separator in (":", "："):
        head, found, tail = text.partition(separator)
        if found and "さん" in head and tail.strip():
            return tail.strip()
    return text


def _categorized_points(
    line: "GeneratedLine",
) -> tuple[
    tuple["GeneratedLanguagePoint", ...],
    tuple["GeneratedLanguagePoint", ...],
    tuple["GeneratedLanguagePoint", ...],
]:
    """Move kana-only points out of the kanji list, which models populate too eagerly."""

    kanji = tuple(point for point in line.kanji if contains_kanji(point.expression))
    misfiled = tuple(
        point for point in line.kanji if not contains_kanji(point.expression)
    )
    return kanji, line.vocabulary + misfiled, line.grammar


def _line_explanation(line: "GeneratedLine", japanese_text: str) -> LessonLineExplanation:
    kanji, vocabulary, grammar = _categorized_points(line)
    return LessonLineExplanation(
        japanese_text=japanese_text,
        english_meaning=line.english_meaning,
        kanji=tuple(_explanation_point(point) for point in kanji),
        vocabulary=tuple(_explanation_point(point) for point in vocabulary),
        grammar=tuple(_explanation_point(point) for point in grammar),
    )


def _explanation_point(point: "GeneratedLanguagePoint") -> LessonExplanationPoint:
    return LessonExplanationPoint(
        expression=point.expression,
        reading=point.reading,
        meaning=point.meaning,
        explanation=point.explanation,
    )


def _dedupe_line_explanations(
    explanations: tuple[LessonLineExplanation, ...],
) -> tuple[LessonLineExplanation, ...]:
    """Keep each expression on its first line so repeated particles stop filling the lesson."""

    seen: set[tuple[str, str]] = set()
    deduped: list[LessonLineExplanation] = []
    for explanation in explanations:
        kept: dict[str, tuple[LessonExplanationPoint, ...]] = {}
        for category in ("kanji", "vocabulary", "grammar"):
            unique: list[LessonExplanationPoint] = []
            for point in getattr(explanation, category):
                key = (category, point.expression)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(point)
            kept[category] = tuple(unique)
        deduped.append(explanation.model_copy(update=kept))
    return tuple(deduped)


def canonical_item_id(
    category: ItemCategory, expression: str, toolkit: LanguageToolkit | None = None
) -> str:
    """Return a stable ID that never stores lesson text in the local database.

    With a toolkit, grammar points map to their curated ID and words to their
    dictionary form, so 連絡します and 連絡 share one item. A word already in
    dictionary form hashes exactly as before, so existing evidence still matches.
    """

    if toolkit is not None:
        if category is ItemCategory.GRAMMAR:
            point = toolkit.grammar_point(expression)
            if point is not None:
                return f"grammar:{point.id}"
        else:
            expression = toolkit.lemma(expression)
    digest = hashlib.sha256(expression.encode("utf-8")).hexdigest()[:16]
    return f"{category.value}:{digest}"


def _reference(category: ItemCategory, expression: str, model_reading: str, toolkit: LanguageToolkit):
    """Level and reading from reference data; absence stays absent (never guessed)."""

    if category is ItemCategory.GRAMMAR:
        point = toolkit.grammar_point(expression)
        if point is None:
            return None, "unrated", 0.0, model_reading
        return jlpt_label(point.level), point.provenance, 0.8, model_reading
    entry = toolkit.lookup(expression)
    accepted = toolkit.readings(expression)
    reading = model_reading
    if accepted and to_hiragana(model_reading) not in accepted:
        # Derived furigana: the dictionary reading replaces a reading it does not accept.
        reading = sorted(entry.readings)[0] if entry and entry.readings else sorted(accepted)[0]
    if entry is None or entry.level is None:
        return None, "unrated", 0.0, reading
    return jlpt_label(entry.level), entry.provenance, 0.8, reading


def _select_target_items(
    explained_lines: Sequence[tuple["GeneratedLine", str]],
    toolkit: LanguageToolkit,
) -> tuple[FixtureItem, ...]:
    """Derive 3-7 unique quiz targets from the language points the model already explained."""

    candidates: list[tuple[FixtureItem, bool]] = []
    seen: set[str] = set()
    for line, example in explained_lines:
        kanji, vocabulary, grammar = _categorized_points(line)
        for category, points in (
            (ItemCategory.KANJI, kanji),
            (ItemCategory.VOCABULARY, vocabulary),
            (ItemCategory.GRAMMAR, grammar),
        ):
            for point in points:
                expression = point.expression.strip()
                if not contains_japanese(expression):
                    continue
                canonical_id = canonical_item_id(category, expression, toolkit)
                if canonical_id in seen:
                    continue
                seen.add(canonical_id)
                level, provenance, confidence, reading = _reference(
                    category, expression, point.reading, toolkit
                )
                candidates.append(
                    (
                        FixtureItem(
                            canonical_id=canonical_id,
                            category=category,
                            expression=expression,
                            reading=reading,
                            meaning=point.meaning,
                            example=example,
                            jlpt_level=level,
                            jlpt_provenance=provenance,
                            jlpt_confidence=confidence,
                        ),
                        point.is_quiz_target,
                    )
                )
    selected = [item for item, is_target in candidates if is_target][:7]
    for item, is_target in candidates:
        if len(selected) >= 3:
            break
        if not is_target:
            selected.append(item)
    if len(selected) < 3:
        raise ValueError("Explain enough Japanese language points to build 3-7 quiz targets.")
    return tuple(selected)


def _lesson_content(
    response: "GeneratedTitledResponse", passage: str, items: tuple[FixtureItem, ...]
) -> LessonContent:
    return LessonContent(
        topic_id=response.topic_id,
        title=response.title,
        difficulty=response.difficulty,
        passage=passage,
        items=items,
        recap=response.recap,
    )


def _validate_lesson_title(content: LessonContent) -> None:
    title_parts = content.title.split(" — ")
    if (
        len(title_parts) != 2
        or not contains_japanese(title_parts[0])
        or not any(character.isascii() and character.isalpha() for character in title_parts[1])
    ):
        raise ValueError(
            "The title must use 'Japanese Title — English Translation' format."
        )


def _validate_generated_conversation(
    content: LessonContent, line_count: int = DEFAULT_LINE_COUNT
) -> None:
    lines = [line.strip() for line in content.passage.splitlines() if line.strip()]
    if len(lines) != line_count:
        raise ValueError(
            f"Generated lessons must contain exactly {line_count} dialogue lines."
        )
    if any("：" in line or ":" not in line for line in lines):
        raise ValueError("Every dialogue line must use 'Nameさん: Japanese dialogue'.")
    if any(not contains_japanese(line.split(":", 1)[1]) for line in lines):
        raise ValueError("Every dialogue line must contain Japanese dialogue.")

    speakers = [line.split(":", 1)[0].strip() for line in lines]
    distinct_speakers = tuple(dict.fromkeys(speakers))
    if len(distinct_speakers) != 2 or any(
        not speaker.endswith("さん") for speaker in distinct_speakers
    ):
        raise ValueError("Generated lessons must use exactly two speakers ending in さん.")
    if any(
        speaker != distinct_speakers[index % 2]
        for index, speaker in enumerate(speakers)
    ):
        raise ValueError(
            f"The two speakers must alternate for exactly {line_count // 2} exchanges."
        )

    names = [speaker.removesuffix("さん") for speaker in distinct_speakers]
    if sum(is_japanese_name(name) for name in names) != 1 or sum(
        is_non_japanese_name(name) for name in names
    ) != 1:
        raise ValueError(
            "Use one Japanese name and one non-Japanese katakana or Latin name."
        )


class LessonGenerator:
    """Scenario and surprise lessons: content first, quiz prepared separately."""

    def __init__(
        self,
        gateway: LLMGateway,
        toolkit: LanguageToolkit,
        parallel_explanations: bool = False,
        explanation_workers: int = 4,
    ) -> None:
        self._toolkit = toolkit
        # v1 accepts only generic or user-attested public text (decision 2), so every
        # lesson task is PUBLIC. Private documents would need a separate PRIVATE task.
        self._run = partial(
            gateway.generate_validated,
            data_class=DataClass.PUBLIC,
            prompt_version=prompts.PROMPT_VERSION,
        )
        self._parallel_explanations = parallel_explanations
        self._explanation_workers = max(1, explanation_workers)

    def generate_lesson_content(
        self,
        scenario: str,
        mode: ScenarioMode,
        profile: ProfileRecord,
        learning_history: Sequence[ProgressRecord] = (),
        recent_topic_ids: Sequence[str] = (),
    ) -> GeneratedLessonDraft:
        try:
            scenario_input = ScenarioInput(scenario=scenario, mode=mode)
        except ValidationError as error:
            raise GenerationError(
                "Enter up to 4,000 characters, with Japanese text required in Explain mode."
            ) from error

        line_count = expected_line_count(profile)
        if self._parallel_explanations:
            package, provider_name = self._generate_split_content(
                scenario_input, profile, learning_history, recent_topic_ids, line_count
            )
            return GeneratedLessonDraft(
                package.lesson,
                package.line_explanations,
                provider_name,
                self._difficulty(package.lesson, profile, learning_history),
            )
        package, provider_name = self._run(
            GeneratedExplanationResponse
            if scenario_input.mode is ScenarioMode.EXPLAIN
            else GeneratedConversationResponse,
            prompts.content_system_prompt(scenario_input.mode, line_count),
            prompts.user_prompt(
                scenario_input, profile, learning_history, recent_topic_ids
            ),
            "lesson_content",
            "We could not generate valid lesson content. Your scenario is still here; please retry.",
            lambda response: self._gate_difficulty(
                self._finalize_content(response, scenario_input, line_count, self._toolkit),
                scenario_input,
                profile,
                learning_history,
            ),
        )
        return GeneratedLessonDraft(
            package.lesson,
            package.line_explanations,
            provider_name,
            self._difficulty(package.lesson, profile, learning_history),
        )

    def generate_quiz(
        self,
        content: LessonContent,
        learning_history: Sequence[ProgressRecord] = (),
    ) -> GeneratedQuiz:
        def finalize(package: GeneratedQuizPackage) -> GeneratedQuizPackage:
            self._validate_quiz_contract(package, content)
            return self._verify_keys(package, content, self._toolkit)

        package, provider_name = self._run(
            GeneratedQuizPackage,
            prompts.quiz_system_prompt(),
            prompts.quiz_user_prompt(content, learning_history),
            "quiz",
            "We could not prepare a valid quiz. Please retry quiz preparation.",
            finalize,
        )
        return GeneratedQuiz(
            package.questions, package.retry_questions, provider_name
        )

    def _generate_split_content(
        self,
        scenario_input: ScenarioInput,
        profile: ProfileRecord,
        learning_history: Sequence[ProgressRecord],
        recent_topic_ids: Sequence[str],
        line_count: int,
    ) -> tuple[GeneratedLessonContentPackage, str]:
        """Fetch the dialogue first, then explain each line concurrently."""

        is_explain = scenario_input.mode is ScenarioMode.EXPLAIN
        header, provider_name = self._run(
            GeneratedExplainHeaderResponse if is_explain else GeneratedDialogueResponse,
            prompts.dialogue_system_prompt(scenario_input.mode, line_count),
            prompts.user_prompt(
                scenario_input, profile, learning_history, recent_topic_ids
            ),
            "lesson_dialogue",
            "We could not generate valid lesson content. Your scenario is still here; please retry.",
            lambda response: response,
        )

        if is_explain:
            texts = tuple(
                line.strip()
                for line in scenario_input.scenario.splitlines()
                if line.strip()
            )
        else:
            texts = tuple(
                _dialogue_text(line.japanese_text)
                for line in header.lines  # type: ignore[union-attr]
            )

        level = profile.estimated_working_level or profile.declared_level
        explanations = self._explain_lines(texts, level)
        lines = tuple(
            GeneratedLine(
                japanese_text=text,
                english_meaning=explanation.english_meaning,
                kanji=explanation.kanji,
                vocabulary=explanation.vocabulary,
                grammar=explanation.grammar,
            )
            for text, explanation in zip(texts, explanations, strict=True)
        )

        if is_explain:
            response: BaseModel = GeneratedExplanationResponse(
                **header.model_dump(), lines=lines
            )
        else:
            response = GeneratedConversationResponse(
                **header.model_dump(exclude={"lines"}), lines=lines
            )
        package = self._gate_difficulty(
            self._finalize_content(response, scenario_input, line_count, self._toolkit),
            scenario_input,
            profile,
            learning_history,
        )
        return package, provider_name

    def _explain_lines(
        self, texts: Sequence[str], level: JapaneseLevel
    ) -> tuple[GeneratedLineExplanationResponse, ...]:
        system_prompt = prompts.line_explanation_system_prompt(level)
        workers = min(self._explanation_workers, max(1, len(texts)))
        pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="line-explanation"
        )
        try:
            futures = [
                pool.submit(
                    self._run,
                    GeneratedLineExplanationResponse,
                    system_prompt,
                    prompts.line_explanation_user_prompt(text),
                    "line_explanation",
                    "We could not explain every line of this lesson. Please retry.",
                    lambda response: response,
                )
                for text in texts
            ]
            return tuple(future.result()[0] for future in futures)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _validate_content_mode(
        package: GeneratedLessonContentPackage,
        scenario_input: ScenarioInput,
        line_count: int = DEFAULT_LINE_COUNT,
    ) -> None:
        _validate_lesson_title(package.lesson)
        if scenario_input.mode is ScenarioMode.EXPLAIN:
            if package.lesson.passage != scenario_input.scenario:
                raise ValueError("Explain mode must preserve the supplied Japanese text exactly.")
            source_line_sequence = tuple(
                line.strip()
                for line in scenario_input.scenario.splitlines()
                if line.strip()
            )
            explained_line_sequence = tuple(
                line.japanese_text.strip() for line in package.line_explanations
            )
            if explained_line_sequence != source_line_sequence:
                raise ValueError(
                    "Explain mode must explain every supplied line exactly and in order."
                )
            source_lines = {
                line.strip()
                for line in scenario_input.scenario.splitlines()
                if line.strip()
            }
            if any(item.example not in source_lines for item in package.lesson.items):
                raise ValueError("Explain-mode item examples must be exact source lines.")
            return

        _validate_generated_conversation(package.lesson, line_count)

    @staticmethod
    def _normalized_content_package(
        package: GeneratedLessonContentPackage, scenario_input: ScenarioInput
    ) -> GeneratedLessonContentPackage:
        if scenario_input.mode is ScenarioMode.EXPLAIN:
            return package
        content = package.lesson.model_copy(
            update={
                "passage": "\n".join(
                    line.japanese_text for line in package.line_explanations
                )
            }
        )
        return package.model_copy(update={"lesson": content})

    MIN_GRADED_QUESTIONS = 2

    @staticmethod
    def _verify_keys(
        package: GeneratedQuizPackage, content: LessonContent, toolkit: LanguageToolkit
    ) -> GeneratedQuizPackage:
        """Grade only keys code can confirm; keep the rest as practice (decision 3)."""

        questions = verify_questions(package.questions, content, toolkit)
        graded = sum(question.graded for question in questions)
        if graded < LessonGenerator.MIN_GRADED_QUESTIONS:
            raise ContractViolation(
                f"Only {graded} of {len(questions)} questions could be checked. Base most "
                "questions on the passage: a reading question whose answer is the dictionary "
                "reading, a meaning question whose answer matches the item's meaning, or a "
                "contextual_cloze whose blank hides the target item in a sentence copied "
                "exactly from the passage."
            )
        return package.model_copy(
            update={
                "questions": questions,
                "retry_questions": verify_questions(package.retry_questions, content, toolkit),
            }
        )

    def _difficulty(
        self,
        content: LessonContent,
        profile: ProfileRecord,
        learning_history: Sequence[ProgressRecord],
    ) -> DifficultyReport:
        mastered = {
            record.item_id for record in learning_history if record.mastery_score >= 0.8
        }

        def is_mastered(lemma: str) -> bool:
            return any(
                canonical_item_id(category, lemma, self._toolkit) in mastered
                for category in (ItemCategory.KANJI, ItemCategory.VOCABULARY)
            )

        level = profile.estimated_working_level or profile.declared_level
        return measure(content.passage, level, self._toolkit, is_mastered)

    def _gate_difficulty(
        self,
        package: GeneratedLessonContentPackage,
        scenario_input: ScenarioInput,
        profile: ProfileRecord,
        learning_history: Sequence[ProgressRecord],
    ) -> GeneratedLessonContentPackage:
        """Reject a generated passage that is far above the learner (not the learner's own text)."""

        if scenario_input.mode is ScenarioMode.EXPLAIN:
            return package
        report = self._difficulty(package.lesson, profile, learning_history)
        if report.too_hard:
            raise ContractViolation(
                f"{round(report.stretch_share * 100)}% of the words are above the learner's "
                f"level ({report.learner_level}). Replace these with simpler words: "
                + "、".join(report.stretch_words[:10])
            )
        return package

    @classmethod
    def _finalize_content(
        cls,
        response: BaseModel,
        scenario_input: ScenarioInput,
        line_count: int,
        toolkit: LanguageToolkit,
    ) -> GeneratedLessonContentPackage:
        if isinstance(response, GeneratedExplanationResponse):
            package = cls._explanation_package(response, scenario_input.scenario, toolkit)
        elif isinstance(response, GeneratedConversationResponse):
            package = cls._conversation_package(response, toolkit)
        else:
            raise TypeError("Unsupported lesson content response.")
        cls._validate_content_mode(package, scenario_input, line_count)
        return package

    @staticmethod
    def _conversation_package(
        response: GeneratedConversationResponse,
        toolkit: LanguageToolkit,
    ) -> GeneratedLessonContentPackage:
        speakers = (
            f"{response.japanese_speaker_name}さん",
            f"{response.other_speaker_name}さん",
        )
        dialogue = [
            (line, _dialogue_text(line.japanese_text), speakers[index % 2])
            for index, line in enumerate(response.lines)
        ]
        line_explanations = _dedupe_line_explanations(
            tuple(
                _line_explanation(line, f"{speaker}: {text}")
                for line, text, speaker in dialogue
            )
        )
        return GeneratedLessonContentPackage(
            lesson=_lesson_content(
                response,
                "\n".join(line.japanese_text for line in line_explanations),
                _select_target_items([(line, text) for line, text, _ in dialogue], toolkit),
            ),
            line_explanations=line_explanations,
        )

    @staticmethod
    def _explanation_package(
        response: GeneratedExplanationResponse, scenario: str, toolkit: LanguageToolkit
    ) -> GeneratedLessonContentPackage:
        explained_lines = [(line, line.japanese_text.strip()) for line in response.lines]
        return GeneratedLessonContentPackage(
            lesson=_lesson_content(
                response, scenario, _select_target_items(explained_lines, toolkit)
            ),
            line_explanations=_dedupe_line_explanations(
                tuple(_line_explanation(line, text) for line, text in explained_lines)
            ),
        )

    @staticmethod
    def _validate_quiz_contract(
        package: GeneratedQuizPackage, content: LessonContent
    ) -> None:
        categories = {item.canonical_id: item.category for item in content.items}
        if any(
            question.item_id not in categories
            for question in (*package.questions, *package.retry_questions)
        ):
            raise ValueError("Every quiz question must reference a lesson target item.")

        covered = Counter(question.item_id for question in package.questions)
        # Kept below the question count so a partial spread degrades instead of failing.
        required_coverage = min(len(package.questions), len(content.items), 4)
        if len(covered) < required_coverage:
            raise ValueError(
                f"Test at least {required_coverage} different lesson items, but only "
                f"{len(covered)} distinct item IDs were used across "
                f"{len(package.questions)} questions."
            )
        if max(covered.values()) > 2:
            raise ValueError(
                "Test no lesson item in more than two questions while other target "
                "items go untested."
            )

        forms = {question.form for question in package.questions}
        if len(forms) < 2:
            raise ValueError(
                "Use at least two different question forms across the quiz."
            )

        for question in (*package.questions, *package.retry_questions):
            lengths = [len(option) for option in question.options]
            if max(lengths) > 5 * min(lengths):
                raise ValueError(
                    "Keep all four options comparable in length so the answer is not "
                    "given away by size."
                )
            if question.form is QuestionForm.READING and not all(
                is_kana_only(option) for option in question.options
            ):
                raise ValueError(
                    "Reading questions must offer four kana-only options."
                )
        if (
            any(categories[item_id] is ItemCategory.GRAMMAR for item_id in covered)
            and QuestionForm.CONTEXTUAL_CLOZE not in forms
        ):
            raise ValueError(
                "Test at least one grammar item with a contextual_cloze question."
            )
