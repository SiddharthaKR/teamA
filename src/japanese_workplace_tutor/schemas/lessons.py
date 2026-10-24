"""Model-facing contracts for lesson content and quizzes (validated before use)."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.items import FixtureQuestion, LessonContent, LessonLineExplanation
from ..core.japanese import contains_japanese, is_japanese_name, is_non_japanese_name


def validate_explanations(
    content: LessonContent,
    line_explanations: tuple[LessonLineExplanation, ...],
    *,
    require_line_match: bool = True,
) -> None:
    passage_lines = tuple(
        line.strip() for line in content.passage.splitlines() if line.strip()
    )
    explained_lines = tuple(
        explanation.japanese_text.strip() for explanation in line_explanations
    )
    if require_line_match and passage_lines != explained_lines:
        raise ValueError(
            "Provide one ordered line explanation for every passage line, using exact text."
        )

    explained_expressions = {
        point.expression
        for explanation in line_explanations
        for points in (
            explanation.kanji,
            explanation.vocabulary,
            explanation.grammar,
        )
        for point in points
    }
    for item in content.items:
        if not contains_japanese(item.expression):
            raise ValueError("Target items must be Japanese language items.")
        if item.expression not in explained_expressions:
            raise ValueError("Every target item must appear in the line explanations.")


class GeneratedLessonContentPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lesson: LessonContent
    line_explanations: tuple[LessonLineExplanation, ...]

    @model_validator(mode="after")
    def validate_explanations(self) -> "GeneratedLessonContentPackage":
        validate_explanations(
            self.lesson, self.line_explanations, require_line_match=False
        )
        return self


class GeneratedQuizPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    questions: tuple[FixtureQuestion, ...] = Field(min_length=4, max_length=6)
    retry_questions: tuple[FixtureQuestion, ...] = Field(min_length=4, max_length=6)

    @model_validator(mode="after")
    def validate_questions(self) -> "GeneratedQuizPackage":
        questions = self.questions
        retries = self.retry_questions
        if not 4 <= len(questions) <= 6:
            raise ValueError("A quiz must contain 4-6 questions.")
        if len(retries) != len(questions):
            raise ValueError("Provide one varied retry for every quiz question.")
        question_ids = [question.question_id for question in questions]
        retry_ids = [retry.question_id for retry in retries]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Quiz question IDs must be unique.")
        if len(retry_ids) != len(set(retry_ids)):
            raise ValueError("Retry question IDs must be unique.")
        if set(question_ids).intersection(retry_ids):
            raise ValueError("Quiz and retry question IDs must be distinct.")
        for question, retry in zip(questions, retries, strict=True):
            if retry.item_id != question.item_id:
                raise ValueError("Each retry must reference its original target item.")
            if retry.form is question.form or retry.prompt == question.prompt:
                raise ValueError("Each retry must use a varied question form and prompt.")
        return self


class GeneratedLanguagePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expression: str = Field(
        min_length=1,
        max_length=100,
        description="One atomic Japanese kanji, word, or grammar pattern, never a whole sentence.",
    )
    reading: str = Field(
        min_length=1, max_length=100, description="Kana reading of the expression."
    )
    meaning: str = Field(
        min_length=1, max_length=200, description="Meaning of the expression, in English."
    )
    explanation: str = Field(
        min_length=1,
        max_length=240,
        description=(
            "One short English sentence teaching how this expression is used here. "
            "Never repeat the expression alone and never answer in Japanese."
        ),
    )
    jlpt_level: str = Field(
        min_length=1, max_length=20, description="Estimated JLPT level, such as 'JLPT N4'."
    )
    is_quiz_target: bool = Field(
        description="True for the 3-7 most useful points in the whole lesson, false otherwise."
    )

    @field_validator("expression", "reading", "meaning", "explanation", "jlpt_level")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_teaching_explanation(self) -> "GeneratedLanguagePoint":
        if self.explanation == self.expression:
            raise ValueError(
                "Every explanation must teach the point instead of repeating the expression."
            )
        return self


class GeneratedLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    japanese_text: str = Field(
        min_length=1,
        description=(
            "Only this speaker's Japanese sentence, with no speaker name, colon, "
            "romaji, translation, or annotation."
        ),
    )
    english_meaning: str = Field(
        min_length=1, description="English translation of japanese_text."
    )
    kanji: tuple[GeneratedLanguagePoint, ...] = Field(
        description=(
            "Kanji words this line introduces for the first time in the lesson. Each "
            "expression must contain at least one kanji character; kana-only words belong "
            "in vocabulary. Empty when the line introduces no new kanji."
        )
    )
    vocabulary: tuple[GeneratedLanguagePoint, ...] = Field(
        description=(
            "Vocabulary expressions this line introduces for the first time in the lesson. "
            "Empty when the line introduces no new vocabulary."
        )
    )
    grammar: tuple[GeneratedLanguagePoint, ...] = Field(
        description=(
            "Grammar patterns this line introduces for the first time in the lesson, "
            "including particles, verb forms, and sentence endings. Empty when the line "
            "introduces no new grammar."
        )
    )


class GeneratedTitledResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: str = Field(
        min_length=1,
        max_length=100,
        description="Short lowercase ASCII identifier for this lesson topic.",
    )
    japanese_title: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "Short lesson title written in Japanese only. Never copy the learner's "
            "scenario text and never use English here."
        ),
    )
    english_title: str = Field(
        min_length=1,
        max_length=100,
        description="English translation of japanese_title, written in English only.",
    )
    difficulty: str = Field(
        min_length=1, max_length=100, description="The learner's JLPT level, such as 'JLPT N4'."
    )
    recap: str = Field(
        min_length=1,
        description="A short English recap of what the learner practised in this lesson.",
    )

    @field_validator("japanese_title")
    @classmethod
    def require_japanese_title(cls, value: str) -> str:
        title = value.strip()
        if not contains_japanese(title):
            raise ValueError("japanese_title must be written in Japanese.")
        return title

    @field_validator("english_title")
    @classmethod
    def require_english_title(cls, value: str) -> str:
        title = value.strip()
        if contains_japanese(title) or not any(
            character.isascii() and character.isalpha() for character in title
        ):
            raise ValueError("english_title must be the English translation of the title.")
        return title

    @property
    def title(self) -> str:
        return f"{self.japanese_title} — {self.english_title}"


class GeneratedSpeakersResponse(GeneratedTitledResponse):
    japanese_speaker_name: str = Field(
        min_length=1,
        max_length=30,
        description="A Japanese personal name written in kanji, without the さん suffix.",
    )
    other_speaker_name: str = Field(
        min_length=1,
        max_length=30,
        description=(
            "A non-Japanese personal name written in katakana or Latin letters, "
            "without the さん suffix."
        ),
    )

    @field_validator("japanese_speaker_name", "other_speaker_name")
    @classmethod
    def normalize_speaker_name(cls, value: str) -> str:
        return value.strip().removesuffix("さん").strip()

    @model_validator(mode="after")
    def validate_speakers(self) -> "GeneratedSpeakersResponse":
        if not is_japanese_name(self.japanese_speaker_name):
            raise ValueError("japanese_speaker_name must be a Japanese name written in kanji.")
        if not is_non_japanese_name(self.other_speaker_name):
            raise ValueError(
                "other_speaker_name must be a non-Japanese name in katakana or Latin letters."
            )
        return self


class GeneratedConversationResponse(GeneratedSpeakersResponse):
    lines: tuple[GeneratedLine, ...] = Field(
        min_length=6,
        max_length=10,
        description=(
            "The requested number of dialogue lines, forming alternating exchanges. "
            "Odd-numbered lines are spoken by the Japanese-named speaker and "
            "even-numbered lines are the other speaker's replies."
        ),
    )


class GeneratedDialogueLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    japanese_text: str = Field(
        min_length=1,
        description=(
            "Only this speaker's Japanese sentence, with no speaker name, colon, "
            "romaji, translation, or annotation."
        ),
    )


class GeneratedDialogueResponse(GeneratedSpeakersResponse):
    lines: tuple[GeneratedDialogueLine, ...] = Field(
        min_length=6,
        max_length=10,
        description=(
            "The requested number of dialogue lines, forming alternating exchanges. "
            "Odd-numbered lines are spoken by the Japanese-named speaker and "
            "even-numbered lines are the other speaker's replies."
        ),
    )


class GeneratedExplainHeaderResponse(GeneratedTitledResponse):
    pass


class GeneratedLineExplanationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    english_meaning: str = Field(
        min_length=1, description="English translation of the supplied Japanese line."
    )
    kanji: tuple[GeneratedLanguagePoint, ...] = Field(
        description=(
            "Kanji words in this line. Each expression must contain at least one kanji "
            "character; kana-only words belong in vocabulary."
        )
    )
    vocabulary: tuple[GeneratedLanguagePoint, ...] = Field(
        description="Vocabulary expressions used in this line."
    )
    grammar: tuple[GeneratedLanguagePoint, ...] = Field(
        description=(
            "Grammar patterns used in this line, including particles, verb forms, and "
            "sentence endings."
        )
    )


class GeneratedExplanationResponse(GeneratedTitledResponse):
    lines: tuple[GeneratedLine, ...] = Field(
        min_length=1,
        max_length=40,
        description=(
            "One entry per non-empty source line, copied character-for-character "
            "into japanese_text and kept in the original order."
        ),
    )


@dataclass(frozen=True)
class GeneratedLessonDraft:
    content: LessonContent
    line_explanations: tuple[LessonLineExplanation, ...]
    provider_name: str


@dataclass(frozen=True)
class GeneratedQuiz:
    questions: tuple[FixtureQuestion, ...]
    retry_questions: tuple[FixtureQuestion, ...]
    provider_name: str
