"""Build the offline MockLLM fixtures in fixtures/llm/ from hand-checked content.

Run from the project root:  python scripts/build_mock_fixtures.py

The fixtures are written by a person, not recorded from a model, so they are a
trustworthy baseline for tests and the offline demo. Item IDs are computed with
the application's own helpers, and every fixture is validated by running the
real LessonGenerationService over MockTransport before anything is written.

Lesson: rescheduling tomorrow's meeting. Quiz targets sit in lines 1-5, so the
6-, 8- and 10-line variants (JLPT N5 / N4 / N3 and above) share one quiz.

The jlpt_level tags below are the author's estimates. Phase 2 replaces them with
lookups against the curated JLPT dataset; until then they are not authoritative.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from japanese_workplace_tutor.generation import (  # noqa: E402
    LessonGenerationService,
    RoleplayVerdict,
    ScenarioMode,
    SituationChallenge,
    _canonical_item_id,
    expected_line_count,
)
from japanese_workplace_tutor.lesson import ItemCategory  # noqa: E402
from japanese_workplace_tutor.llm_mock import MockTransport  # noqa: E402
from japanese_workplace_tutor.profile import (  # noqa: E402
    JapaneseLevel,
    LevelSource,
    ProfileRecord,
)

FIXTURE_DIR = ROOT / "fixtures" / "llm"


def point(expression, reading, meaning, explanation, level, target=False):
    return {
        "expression": expression,
        "reading": reading,
        "meaning": meaning,
        "explanation": explanation,
        "jlpt_level": level,
        "is_quiz_target": target,
    }


def line(text, english, kanji=(), vocabulary=(), grammar=()):
    return {
        "japanese_text": text,
        "english_meaning": english,
        "kanji": list(kanji),
        "vocabulary": list(vocabulary),
        "grammar": list(grammar),
    }


LINES = [
    line(
        "リンさん、明日の会議の時間を変えてもいいですか。",
        "Lin, may I change the time of tomorrow's meeting?",
        kanji=[point("会議", "かいぎ", "meeting", "A scheduled work meeting with colleagues.", "JLPT N4", True)],
        vocabulary=[point("変える", "かえる", "to change", "Used here for moving the meeting to another time.", "JLPT N4")],
        grammar=[point("〜てもいいですか", "てもいいですか", "May I ...?", "Te-form plus もいいですか politely asks for permission.", "JLPT N5", True)],
    ),
    line(
        "はい、大丈夫です。何時がいいですか。",
        "Yes, that's fine. What time would be good?",
        vocabulary=[
            point("大丈夫", "だいじょうぶ", "all right; no problem", "A polite way to say a change is acceptable.", "JLPT N4"),
            point("何時", "なんじ", "what time", "Asks for a clock time when agreeing on a schedule.", "JLPT N5"),
        ],
    ),
    line(
        "午後三時からはどうですか。",
        "How about from 3 p.m.?",
        kanji=[point("午後", "ごご", "afternoon; p.m.", "Marks a time after noon.", "JLPT N5")],
        grammar=[point("〜はどうですか", "はどうですか", "How about ...?", "Suggests an option and invites the listener to decide.", "JLPT N5", True)],
    ),
    line(
        "三時ですね。では、それまでに準備しておきます。",
        "Three o'clock, right? Then I'll get things ready by then.",
        kanji=[point("準備", "じゅんび", "preparation", "準備する means to get things ready for the meeting.", "JLPT N4", True)],
        vocabulary=[point("それまでに", "それまでに", "by then", "Sets the deadline as the agreed meeting time.", "JLPT N4")],
        grammar=[point("〜ておきます", "ておきます", "do in advance", "Te-form plus おきます means doing something ahead of time.", "JLPT N4", True)],
    ),
    line(
        "ありがとうございます。ほかの人にも連絡します。",
        "Thank you. I'll contact the others too.",
        kanji=[point("連絡", "れんらく", "contact; getting in touch", "連絡する means to let people know about the change.", "JLPT N4", True)],
        vocabulary=[point("ほかの人", "ほかのひと", "other people", "Refers to the other meeting attendees.", "JLPT N4")],
    ),
    line(
        "はい、よろしくお願いします。",
        "Yes, thank you for handling that.",
        vocabulary=[point("よろしくお願いします", "よろしくおねがいします", "thank you in advance", "A standard polite close when someone will take action.", "JLPT N5")],
    ),
    line(
        "それから、会議室も予約してもらえますか。",
        "Also, could you book the meeting room?",
        kanji=[
            point("会議室", "かいぎしつ", "meeting room", "The room reserved for the meeting.", "JLPT N4"),
            point("予約", "よやく", "reservation; booking", "予約する means to book the room in advance.", "JLPT N4"),
        ],
        grammar=[point("〜てもらえますか", "てもらえますか", "Could you ...?", "Te-form plus もらえますか politely asks someone for a favour.", "JLPT N4")],
    ),
    line(
        "分かりました。すぐ予約します。",
        "Understood. I'll book it right away.",
        vocabulary=[
            point("分かりました", "わかりました", "understood", "Confirms a request politely.", "JLPT N5"),
            point("すぐ", "すぐ", "right away", "Says the action will happen immediately.", "JLPT N5"),
        ],
    ),
    line(
        "助かります。何かあったら、いつでも聞いてください。",
        "That helps. If anything comes up, ask me any time.",
        vocabulary=[point("助かります", "たすかります", "that helps; thank you", "Thanks someone by saying their help makes things easier.", "JLPT N3")],
        grammar=[point("〜たら", "たら", "if; when", "Ta-form plus ら sets a condition: if something happens.", "JLPT N4")],
    ),
    line(
        "はい、ありがとうございます。",
        "Yes, thank you.",
        vocabulary=[point("ありがとうございます", "ありがとうございます", "thank you", "The polite form of thanks.", "JLPT N5")],
    ),
]

TARGETS = {
    "kaigi": (ItemCategory.KANJI, "会議"),
    "temoii": (ItemCategory.GRAMMAR, "〜てもいいですか"),
    "wadou": (ItemCategory.GRAMMAR, "〜はどうですか"),
    "junbi": (ItemCategory.KANJI, "準備"),
    "teoku": (ItemCategory.GRAMMAR, "〜ておきます"),
    "renraku": (ItemCategory.KANJI, "連絡"),
}
ID = {key: _canonical_item_id(category, expression) for key, (category, expression) in TARGETS.items()}


def question(qid, key, form, prompt, options, explanation):
    return {
        "question_id": qid,
        "item_id": ID[key],
        "form": form,
        "prompt": prompt,
        "options": options,
        "correct_option_index": 0,
        "explanation": explanation,
    }


QUIZ = {
    "questions": [
        question("q-kaigi-meaning", "kaigi", "meaning", "What does 会議 mean?",
                 ["meeting", "schedule", "report", "contract"], "会議 (かいぎ) means a meeting."),
        question("q-temoii-cloze", "temoii", "contextual_cloze",
                 "Choose the ending that asks permission: 時間を変え___。",
                 ["てもいいですか", "てはいけません", "ないでください", "たことがあります"],
                 "変えてもいいですか asks whether it is all right to change the time."),
        question("q-wadou-meaning", "wadou", "meaning",
                 "What does 〜はどうですか do in 午後三時からはどうですか。?",
                 ["Suggests an option", "Asks for a reason", "Gives a warning", "Reports a result"],
                 "〜はどうですか proposes an option (3 p.m.) for the listener to accept."),
        question("q-junbi-reading", "junbi", "reading", "How is 準備 read?",
                 ["じゅんび", "じゅんぴ", "しゅんび", "じゅうび"], "準備 is read じゅんび."),
        question("q-teoku-cloze", "teoku", "contextual_cloze",
                 "Choose the ending that means 'get ready in advance': それまでに準備し___。",
                 ["ておきます", "てしまいました", "たいです", "ませんでした"],
                 "準備しておきます means preparing ahead of the meeting."),
        question("q-renraku-meaning", "renraku", "meaning", "What does 連絡します mean?",
                 ["to contact someone", "to cancel something", "to book a room", "to wait for someone"],
                 "連絡します (れんらくします) means to get in touch with someone."),
    ],
    "retry_questions": [
        question("r-kaigi-reading", "kaigi", "reading", "How is 会議 read?",
                 ["かいぎ", "かいき", "がいぎ", "かいご"], "会議 is read かいぎ."),
        question("r-temoii-meaning", "temoii", "meaning", "What does 〜てもいいですか express?",
                 ["Asking permission", "Giving an order", "Refusing a request", "Describing the past"],
                 "〜てもいいですか asks for permission."),
        question("r-wadou-cloze", "wadou", "contextual_cloze",
                 "Choose the ending that proposes a time: 明日の十時___。",
                 ["はどうですか", "はだめでした", "までです", "からです"],
                 "明日の十時はどうですか proposes 10 o'clock tomorrow."),
        question("r-junbi-meaning", "junbi", "meaning", "What does 準備 mean?",
                 ["preparation", "reservation", "contact", "change"],
                 "準備 means preparation; 予約 is a reservation and 連絡 is contact."),
        question("r-teoku-meaning", "teoku", "meaning", "What does 〜ておきます add to 準備します?",
                 ["Doing it in advance", "Doing it by mistake", "Wanting to do it", "Being unable to do it"],
                 "〜ておきます means doing something ahead of time."),
        question("r-renraku-reading", "renraku", "reading", "How is 連絡 read?",
                 ["れんらく", "れんあく", "れいらく", "ねんらく"], "連絡 is read れんらく."),
    ],
}

LEVEL_FOR_COUNT = {6: "JLPT N5", 8: "JLPT N4", 10: "JLPT N3"}


def conversation(count: int) -> dict[str, object]:
    return {
        "topic_id": "meeting-reschedule",
        "japanese_title": "会議の時間の変更",
        "english_title": "Changing a Meeting Time",
        "difficulty": LEVEL_FOR_COUNT[count],
        "recap": "You practised asking permission, proposing a time and promising to prepare in advance.",
        "japanese_speaker_name": "田中",
        "other_speaker_name": "リン",
        "lines": LINES[:count],
    }


CHALLENGE = {
    "goal": "Agree on a new meeting time with your manager and offer to prepare",
    "setting": "Your manager stops by your desk the afternoon before the meeting",
    "learner_role": "team member",
    "counterpart_role": "your manager",
    "success_criteria": [
        "accept or propose a concrete time",
        "use polite です/ます forms",
        "offer to prepare in advance",
    ],
    "toolkit": [
        {"japanese": "〜はどうですか", "reading": "はどうですか", "meaning": "How about ...?", "kind": "target"},
        {"japanese": "準備しておきます", "reading": "じゅんびしておきます", "meaning": "I'll prepare in advance", "kind": "target"},
        {"japanese": "もう一度お願いします", "reading": "もういちどおねがいします", "meaning": "Once more, please", "kind": "recovery"},
    ],
    "opening_line": "明日の会議、時間を変えてもいいですか。",
    "opening_options": [
        "はい、大丈夫です。何時がいいですか。",
        "うん、いいよ。",
        "会議はいやです。",
    ],
    "curveball_type": "follow-up request",
    "curveball_line": "それから、資料も準備してもらえますか。",
    "curveball_options": [
        "はい、三時までに準備しておきます。",
        "え、なんで？",
        "資料は好きじゃないです。",
    ],
}

VERDICT = {
    "goal_achieved": True,
    "goal_evidence": "The learner accepted the change and asked for a time.",
    "comprehensible": "yes",
    "comprehensible_evidence": "Both replies were clear and complete.",
    "register_appropriate": True,
    "register_evidence": "Polite です/ます forms were used throughout.",
    "recovered_from_curveball": "yes",
    "recovery_evidence": "The learner agreed to prepare the materials by a stated time.",
}


def fixtures() -> dict[str, list[dict[str, object]]]:
    return {
        "GeneratedConversationResponse": [
            {"match": [f"Write exactly {count} dialogue lines"], "response": conversation(count)}
            for count in (6, 8, 10)
        ],
        "GeneratedQuizPackage": [{"match": [], "response": QUIZ}],
        "SituationChallenge": [{"match": [], "response": CHALLENGE}],
        "RoleplayVerdict": [{"match": [], "response": VERDICT}],
    }


def _profile(level: JapaneseLevel) -> ProfileRecord:
    return ProfileRecord(
        user_id=1, role="Software engineer", tasks=("Attend meetings",), tools_domain=None,
        declared_level=level, estimated_working_level=None,
        level_source=LevelSource.SELF_REPORTED, level_confidence=1.0, romaji_preference=False,
    )


def verify(fixture_dir: Path) -> None:
    """Run the real service over the fixtures for every learner level."""

    SituationChallenge.model_validate(CHALLENGE)
    RoleplayVerdict.model_validate(VERDICT)
    for level in JapaneseLevel:
        service = LessonGenerationService(MockTransport(fixture_dir), "mock-primary", "mock-fallback")
        draft = service.generate_lesson_content("", ScenarioMode.GENERATE, _profile(level))
        lines = [row for row in draft.content.passage.splitlines() if row.strip()]
        assert len(lines) == expected_line_count(_profile(level)), level
        assert {item.canonical_id for item in draft.content.items} == set(ID.values()), level
        quiz = service.generate_quiz(draft.content)
        assert len(quiz.questions) == 6
        service.generate_situation_challenge(draft.content, _profile(level))


def main() -> None:
    data = fixtures()
    with tempfile.TemporaryDirectory() as scratch:
        for title, entries in data.items():
            (Path(scratch) / f"{title}.json").write_text(
                json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        verify(Path(scratch))
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for title, entries in data.items():
        (FIXTURE_DIR / f"{title}.json").write_text(
            json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Wrote {len(data)} fixture files to {FIXTURE_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
