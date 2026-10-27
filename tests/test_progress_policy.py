"""The progress policy is a pure function of evidence and can be replayed."""

from datetime import datetime, timedelta

from japanese_workplace_tutor.core.items import (
    AnswerConfidence,
    ItemCategory,
    QuestionForm,
    ReviewOutcome,
)
from japanese_workplace_tutor.core.progress import (
    Answer,
    SM2MasteryPolicy,
    replay,
    skill_dimension,
)

POLICY = SM2MasteryPolicy()
START = datetime(2026, 11, 1, 9, 0)


def answer(day: int, session: str, form: QuestionForm, *, correct: bool = True, retry: bool = False,
           confidence: AnswerConfidence = AnswerConfidence.SURE) -> Answer:
    return Answer(
        question_form=form,
        skill_dimension=skill_dimension(form, ItemCategory.VOCABULARY),
        lesson_session_id=session,
        is_correct=correct,
        is_retry=retry,
        confidence=confidence,
        answered_at=START + timedelta(days=day),
    )


GOLDEN_LOG = (
    answer(0, "s1", QuestionForm.MEANING, correct=False),
    answer(0, "s1", QuestionForm.CONTEXTUAL_CLOZE, retry=True),
    answer(1, "s2", QuestionForm.READING),
    answer(4, "s3", QuestionForm.MEANING),
    answer(11, "s4", QuestionForm.CONTEXTUAL_CLOZE),
    answer(33, "s5", QuestionForm.READING),
)


def test_readme_golden_vectors_replay_exactly() -> None:
    states = [replay(POLICY, GOLDEN_LOG[:count])[0] for count in range(1, len(GOLDEN_LOG) + 1)]
    _, outcomes = replay(POLICY, GOLDEN_LOG)
    masteries = [state.mastery_score for state in states]
    eases = [state.sm2_ease for state in states]
    intervals = [state.sm2_interval_days for state in states]

    assert list(outcomes) == [
        ReviewOutcome.AGAIN, ReviewOutcome.HARD, ReviewOutcome.GOOD,
        ReviewOutcome.GOOD, ReviewOutcome.EASY, ReviewOutcome.EASY,
    ]
    assert masteries == [0.0, 0.08, 0.26, 0.44, 0.74, 1.0]
    assert eases == [2.3, 2.15, 2.2, 2.25, 2.4, 2.55]
    assert intervals == [0, 1, 3, 7, 22, 73]


def test_replay_is_deterministic() -> None:
    assert replay(POLICY, GOLDEN_LOG) == replay(POLICY, GOLDEN_LOG)


def test_guessed_answers_never_earn_easy_and_count_half() -> None:
    sure_log = GOLDEN_LOG[:4] + (answer(11, "s4", QuestionForm.CONTEXTUAL_CLOZE),)
    guessed_log = GOLDEN_LOG[:4] + (
        answer(11, "s4", QuestionForm.CONTEXTUAL_CLOZE, confidence=AnswerConfidence.GUESSED),
    )

    sure_state, sure_outcomes = replay(POLICY, sure_log)
    guessed_state, guessed_outcomes = replay(POLICY, guessed_log)

    assert sure_outcomes[-1] is ReviewOutcome.EASY
    assert guessed_outcomes[-1] is ReviewOutcome.GOOD
    assert guessed_state.mastery_score < sure_state.mastery_score


def test_single_form_success_cannot_master_an_item() -> None:
    same_form = tuple(answer(day, f"s{day}", QuestionForm.MEANING) for day in (0, 1, 4, 11, 33))

    state, _ = replay(POLICY, same_form)

    assert state.mastery_score < POLICY.MASTERY_THRESHOLD
