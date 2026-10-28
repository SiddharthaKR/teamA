"""Phase 2 trust layer: reference data, item identity, verified keys, difficulty."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from japanese_workplace_tutor.core.difficulty import MAX_STRETCH_SHARE, measure
from japanese_workplace_tutor.core.items import KeySource, QuestionForm
from japanese_workplace_tutor.core.language import reference_label
from japanese_workplace_tutor.core.verification import verify_question
from japanese_workplace_tutor.features.lessons import canonical_item_id
from japanese_workplace_tutor.generation import LessonGenerationService, ScenarioMode
from japanese_workplace_tutor.language.sudachi_toolkit import SudachiToolkit
from japanese_workplace_tutor.lesson import FIXTURE_LESSON, ItemCategory, LessonService
from japanese_workplace_tutor.llm.mock import MockTransport
from japanese_workplace_tutor.profile import JapaneseLevel
from japanese_workplace_tutor.schemas.lessons import GeneratedQuizPackage

from test_generation import profile
from test_lesson import create_services

TOOLKIT = SudachiToolkit.shared()
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"


def mock_draft(level: JapaneseLevel = JapaneseLevel.N4):
    service = LessonGenerationService(MockTransport(FIXTURES), "mock-primary", "mock-fallback")
    return service, service.generate_lesson_content("", ScenarioMode.GENERATE, profile(level))


def test_reference_data_corrects_known_dataset_errors() -> None:
    assert TOOLKIT.lookup("ありがとう").level == "N5"
    assert TOOLKIT.lookup("いい").provenance == "override-v1"
    assert TOOLKIT.lookup("会議").level == "N4"
    assert "じゅんび" in TOOLKIT.readings("準備")
    assert {"あした", "あす"} <= TOOLKIT.readings("明日")


def test_tanos_list_is_primary_and_openjlpt_only_fills_gaps() -> None:
    assert TOOLKIT.lookup("会議").provenance == "tanos-v1"
    assert TOOLKIT.lookup("締め切り").level == "N2"  # OpenJLPT says N1
    assert TOOLKIT.lookup("打ち合わせ").provenance.startswith("openjlpt")  # not in tanos
    assert "tanos-v1" in TOOLKIT.version and "business-v1" in TOOLKIT.version


def test_business_list_tags_workplace_words_and_keeps_jlpt_levels() -> None:
    shared = TOOLKIT.lookup("共有")
    assert shared.level is None and shared.business_group == "meetings"
    assert reference_label(shared) == "Business Japanese"
    meeting = TOOLKIT.lookup("会議")
    assert meeting.business_group == "meetings" and reference_label(meeting) == "JLPT N4"
    assert TOOLKIT.lookup("お疲れ様です").business_group == "phrases"


def test_alternate_spellings_share_one_item() -> None:
    assert TOOLKIT.lemma("打合せ") == "打ち合わせ"
    assert canonical_item_id(ItemCategory.VOCABULARY, "締切", TOOLKIT) == canonical_item_id(
        ItemCategory.VOCABULARY, "締め切り", TOOLKIT
    )


def test_business_words_are_in_section_for_any_level() -> None:
    passage = "明日の打ち合わせの資料を共有します。進捗はメールで報告します。議事録も送信します。"
    report = measure(passage, JapaneseLevel.N5, TOOLKIT)

    assert report.stretch == 0
    assert report.business >= 6
    assert report.in_section_share == 1.0


def test_non_business_words_above_level_still_stretch() -> None:
    report = measure("彼の主張は矛盾を孕んでいる。", JapaneseLevel.N5, TOOLKIT)

    assert report.business == 0
    assert report.stretch >= 2


def test_grammar_points_match_model_spellings() -> None:
    for spelling in ("〜ておきます", "ておく", "〜ておきます (do in advance)", "ておきました"):
        assert TOOLKIT.grammar_point(spelling).id == "te-oku"
    assert TOOLKIT.grammar_point("〜てもいいですか").level == "N5"


def test_inflected_words_share_one_item_and_dictionary_forms_keep_old_ids() -> None:
    assert canonical_item_id(ItemCategory.KANJI, "連絡します", TOOLKIT) == canonical_item_id(
        ItemCategory.KANJI, "連絡", TOOLKIT
    )
    # A word already in dictionary form hashes exactly as the hackathon build did.
    assert canonical_item_id(ItemCategory.KANJI, "会議", TOOLKIT) == canonical_item_id(
        ItemCategory.KANJI, "会議"
    )
    assert canonical_item_id(ItemCategory.GRAMMAR, "〜てもいいですか", TOOLKIT) == "grammar:te-mo-ii"


def test_levels_come_from_reference_data_never_from_the_model() -> None:
    _, draft = mock_draft()
    items = {item.expression: item for item in draft.content.items}

    assert items["会議"].jlpt_provenance == "tanos-v1"
    assert items["〜ておきます"].jlpt_provenance == "grammar-list-v1"
    assert all(item.jlpt_provenance != "model-estimate" for item in items.values())


def test_off_passage_cloze_is_practice_only_and_the_rest_are_graded() -> None:
    service, draft = mock_draft()
    quiz = service.generate_quiz(draft.content)

    assert all(question.key_source is KeySource.DERIVED for question in quiz.questions)
    sources = {retry.question_id: retry.key_source for retry in quiz.retry_questions}
    assert sources["r-wadou-cloze"] is KeySource.UNVERIFIED  # 明日の十時 is not in the passage
    assert sum(source is KeySource.DERIVED for source in sources.values()) == 5


def _quiz_question(question_id: str):
    entries = json.loads((FIXTURES / "GeneratedQuizPackage.json").read_text(encoding="utf-8"))
    package = GeneratedQuizPackage.model_validate(entries[0]["response"])
    return next(q for q in (*package.questions, *package.retry_questions) if q.question_id == question_id)


def test_wrong_model_key_is_not_graded() -> None:
    _, draft = mock_draft()
    reading = _quiz_question("q-junbi-reading")
    wrong_key = reading.model_copy(update={"correct_option_index": 1})  # じゅんぴ

    assert verify_question(reading, draft.content, TOOLKIT) is KeySource.DERIVED
    assert verify_question(wrong_key, draft.content, TOOLKIT) is KeySource.UNVERIFIED


def test_ambiguous_reading_question_is_not_graded() -> None:
    _, draft = mock_draft()
    item = draft.content.items[0]
    question = _quiz_question("r-kaigi-reading").model_copy(
        update={"options": ("あした", "あす", "みょうにち", "あさ"), "correct_option_index": 0}
    )
    content = draft.content.model_copy(
        update={"items": (item.model_copy(update={"expression": "明日"}), *draft.content.items[1:])}
    )

    assert verify_question(question, content, TOOLKIT) is KeySource.UNVERIFIED


def test_meaning_distractor_that_is_also_right_blocks_grading() -> None:
    _, draft = mock_draft()
    question = _quiz_question("q-kaigi-meaning").model_copy(
        update={"options": ("meeting", "a meeting with clients", "report", "contract")}
    )

    assert verify_question(question, draft.content, TOOLKIT) is KeySource.UNVERIFIED


def test_register_questions_are_never_graded_by_code() -> None:
    _, draft = mock_draft()
    question = _quiz_question("q-kaigi-meaning").model_copy(update={"form": QuestionForm.REGISTER})

    assert verify_question(question, draft.content, TOOLKIT) is KeySource.UNVERIFIED


def test_key_source_is_hidden_from_the_model_schema() -> None:
    schema = json.dumps(GeneratedQuizPackage.model_json_schema())

    assert "key_source" not in schema


def test_difficulty_report_scales_with_learner_level() -> None:
    _, draft = mock_draft(JapaneseLevel.N3)
    passage = draft.content.passage

    n5 = measure(passage, JapaneseLevel.N5, TOOLKIT)
    n3 = measure(passage, JapaneseLevel.N3, TOOLKIT)

    assert n5.stretch_share > n3.stretch_share
    assert not n3.too_hard
    assert MAX_STRETCH_SHARE == 0.5


def test_mastered_words_count_as_familiar() -> None:
    _, draft = mock_draft(JapaneseLevel.N5)
    passage = draft.content.passage

    plain = measure(passage, JapaneseLevel.N5, TOOLKIT)
    helped = measure(passage, JapaneseLevel.N5, TOOLKIT, lambda lemma: lemma == "変える")

    assert helped.stretch == plain.stretch - 1


def test_draft_carries_its_difficulty_report() -> None:
    _, draft = mock_draft(JapaneseLevel.N4)

    assert draft.difficulty is not None
    assert draft.difficulty.learner_level == "JLPT N4"
    assert draft.difficulty.rated > 0


def test_practice_answers_are_logged_but_never_change_progress(tmp_path: Path) -> None:
    auth, lessons, engine = create_services(tmp_path / "lesson.db")
    user = auth.register("Alice", "correct horse battery staple")
    active = lessons.start_fixture_lesson(user.id)
    question = active.lesson.questions[0]
    practice = question.model_copy(update={"key_source": KeySource.UNVERIFIED})
    practice_lesson = active.lesson.model_copy(
        update={"questions": (practice, *active.lesson.questions[1:])}
    )
    practice_active = replace(active, lesson=practice_lesson)
    before = {record.item_id: record for record in lessons.get_progress(user.id)}

    result = lessons.submit_answer(
        user.id,
        active.lesson_session_id,
        practice.question_id,
        practice.correct_option_index,
        active_lesson=practice_active,
    )

    after = {record.item_id: record for record in lessons.get_progress(user.id)}
    assert result.graded is False
    assert result.is_correct is True
    assert after[practice.item_id].mastery_score == before[practice.item_id].mastery_score
    assert after[practice.item_id].correct_count == before[practice.item_id].correct_count
    assert after[practice.item_id].next_review_at == before[practice.item_id].next_review_at
    engine.dispose()


def test_fixture_lesson_questions_are_curated_and_graded() -> None:
    assert all(question.key_source is KeySource.CURATED for question in FIXTURE_LESSON.questions)
    assert LessonService.POLICY_VERSION == "t05-v2"


@pytest.mark.parametrize("level", list(JapaneseLevel))
def test_mock_lesson_passes_the_difficulty_gate_for_every_level(level) -> None:
    _, draft = mock_draft(level)

    assert not draft.difficulty.too_hard
