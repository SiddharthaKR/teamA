"""Learning items, questions and lesson content: the domain's core value types."""

from enum import StrEnum
from hashlib import sha256
from random import Random

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ItemCategory(StrEnum):
    KANJI = "kanji"
    VOCABULARY = "vocabulary"
    GRAMMAR = "grammar"


class QuestionForm(StrEnum):
    MEANING = "meaning"
    READING = "reading"
    CONTEXTUAL_CLOZE = "contextual_cloze"
    REGISTER = "register"


class AnswerConfidence(StrEnum):
    SURE = "sure"
    GUESSED = "guessed"


class SkillDimension(StrEnum):
    RECOGNITION = "recognition"
    READING = "reading"
    CONTEXTUAL_USE = "contextual_use"
    GRAMMAR_APPLICATION = "grammar_application"


class ReviewOutcome(StrEnum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class FixtureItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_id: str = Field(min_length=1, max_length=128)
    category: ItemCategory
    expression: str = Field(min_length=1)
    reading: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    example: str = Field(min_length=1)
    jlpt_level: str | None
    jlpt_provenance: str
    jlpt_confidence: float = Field(ge=0.0, le=1.0)


class FixtureQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1, max_length=64)
    item_id: str
    form: QuestionForm
    prompt: str = Field(min_length=1)
    options: tuple[str, ...] = Field(min_length=4, max_length=4)
    correct_option_index: int = Field(ge=0, le=3)
    # Self-checking answer key. When a generator supplies the correct option's
    # exact text here, the position is resolved deterministically below instead of
    # trusting a hand-counted index a small model can miscount (or that silently
    # drifts if it reorders the options). Fixtures omit it and keep their index.
    # Excluded from serialization so it never lands in a persisted dump.
    correct_value: str | None = Field(default=None, exclude=True)
    explanation: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _resolve_correct_value(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        value = data.get("correct_value")
        options = data.get("options")
        if value is None or not isinstance(options, (list, tuple)):
            return data
        normalized = [str(option).strip() for option in options]
        target = str(value).strip()
        if target not in normalized:
            raise ValueError(
                "correct_value must exactly match one of the options."
            )
        return {**data, "correct_option_index": normalized.index(target)}

    @model_validator(mode="after")
    def validate_options(self) -> "FixtureQuestion":
        # Answers are resolved by option text, so duplicates would be ambiguous.
        if len(set(self.options)) != len(self.options):
            raise ValueError("Question options must be distinct.")
        return self


def display_options(question: FixtureQuestion) -> tuple[str, ...]:
    """Shuffle option order for display only, keyed so Streamlit reruns stay stable."""

    seed = int(sha256(question.question_id.encode("utf-8")).hexdigest()[:16], 16)
    options = list(question.options)
    Random(seed).shuffle(options)
    return tuple(options)


class LessonExplanationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expression: str = Field(min_length=1)
    reading: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class LessonLineExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    japanese_text: str = Field(min_length=1)
    english_meaning: str = Field(min_length=1)
    kanji: tuple[LessonExplanationPoint, ...]
    vocabulary: tuple[LessonExplanationPoint, ...]
    grammar: tuple[LessonExplanationPoint, ...]


class LessonContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    difficulty: str = Field(min_length=1, max_length=128)
    passage: str = Field(min_length=1)
    items: tuple[FixtureItem, ...] = Field(min_length=3, max_length=7)
    recap: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_items(self) -> "LessonContent":
        item_ids = [item.canonical_id for item in self.items]
        if not 3 <= len(item_ids) <= 7:
            raise ValueError("A lesson must contain 3-7 target items.")
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Lesson item IDs must be unique.")
        return self


class FixtureLesson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    difficulty: str = Field(min_length=1, max_length=128)
    passage: str = Field(min_length=1)
    items: tuple[FixtureItem, ...]
    questions: tuple[FixtureQuestion, ...]
    recap: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_lesson(self) -> "FixtureLesson":
        item_ids = [item.canonical_id for item in self.items]
        question_ids = [question.question_id for question in self.questions]
        if not 3 <= len(item_ids) <= 7:
            raise ValueError("A lesson must contain 3-7 target items.")
        if not 4 <= len(question_ids) <= 6:
            raise ValueError("A lesson must contain 4-6 questions.")
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Lesson item IDs must be unique.")
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Lesson question IDs must be unique.")
        if any(question.item_id not in item_ids for question in self.questions):
            raise ValueError("Every question must reference a lesson item.")
        return self
