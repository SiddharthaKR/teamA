# Tasks for the next agent (Phase 2 fixes, Phases 3–5)

Hand-off written 2026-10-25. Work continues on branch `v2`. Each task has a goal, where to look, and when it is done. Decisions are numbered as in `docs/design/architecture-v2.md` (the full design, exported from the original doc).

## Read first

| File | Why |
| --- | --- |
| `docs/handoff/PLAN.md` | The phase plan as reviewed by the team; check its review table and answers before starting a phase |
| `docs/design/architecture-v2.md` | The design: trust tiers, phases, decisions 1–16 |
| `docs/ux-review/README.md` | UX walkthrough with screenshots and a 16-row fix list |
| `docs/architecture/graph.json`, `docs/architecture/architecture.html` | System map (blocks, wires, external tech), checked against the code |
| `README.md` | How to run, settings (`JLT_*`), migrations |
| `THIRD_PARTY_NOTICES.md` | Licences of the bundled word lists |

## Ground rules

- **The model proposes, the code decides.** Anything graded, stored as a fact or shown as authoritative comes from curated data or a code check, never straight from the model. Questions whose key code cannot verify are practice only (`KeySource.UNVERIFIED`, logged with `is_graded=false`).
- **`core/` stays pure**: no IO, UI, database or SDK imports. `import-linter` contracts in `pyproject.toml` enforce the layers; `tests/test_architecture.py` runs them.
- **Keep the system map in sync.** Every new module goes into a block in `docs/architecture/graph.json`, with `depends` wires for new cross-block imports and a `tech` entry for new third-party packages. Run `python scripts/archmap.py check`, then `python scripts/archmap.py build`; `tests/test_architecture_graph.py` fails on drift. Add a `changelog` entry.
- **Prompts** are Python modules with `PROMPT_VERSION` and byte-for-byte snapshot tests (`tests/test_prompts.py`). Changing a prompt means bumping its version and updating the snapshot on purpose.
- **Progress is replayed from evidence.** Answers in `review_attempts` are append-only; mastery comes from a versioned policy (`core/progress.py`, now `t05-v1`). A policy change gets a new version and must replay old evidence.
- **Privacy (decision 2).** Only content the user confirms is public goes to OpenAI. Every prompt task is tagged `PUBLIC`/`PRIVATE`. Never commit `.env` (it holds a real key). Record mode is for public inputs only.
- **Schema changes** go through Alembic (`alembic/versions/`, head `20261024_0009`) with a test in `tests/test_migrations.py`.
- **Tests**: `JLT_MODEL_BASE_URL=http://127.0.0.1:9 python -m pytest` (323 tests, no network; the URL blocks accidental live calls). Run the app offline with `JLT_LLM_MODE=mock`; `JLT_REVIEWER_MODE=true` shows the accuracy tools.
- Keep each file's existing line endings (some files are CRLF in git).

## A. Fix before the team accuracy review

From the UX review fix list. A1 and A2 first: they inflate exactly the numbers the team will judge.

Why these matter (learning, 2026-10-25): memory fades roughly as R(t) = e^(−t/S); stability S grows most from recall after a gap and from producing an answer rather than recognising it. A1/A2 keep that honest; C8–C12 add production and context.

| ID | Task | Where | Done when |
| --- | --- | --- | --- |
| A1 | Hide the lesson (conversation, breakdown, glossary) while the quiz is open; stop printing the answer in fill-in questions | `app.py` lesson and quiz rendering (`st.caption(f"From the lesson: …")`, around line 889) | Quiz view shows only questions; cloze context has the answer blanked; app test covers it |
| A2 | Mastery needs successes on separate **days** (Japan time), not separate sessions | `core/progress.py` `SM2MasteryPolicy.outcome` (uses `lesson_session_id`); add `answered_at` to `PastAttempt`; new policy version `t05-v2`; `LessonService.POLICY_VERSION`; Progress caption in `app.py` | Three same-day lessons cannot reach Easy; replay of old evidence works; tests in `test_progress_policy.py` and `test_progress_history.py` |
| A3 | Remove developer wording for learners: "Demo authentication", "fixture", "records exposure only", "Outcome: Easy/Hard", "Source: …", "Contextual Cloze", "compact progress", "Recovery is stored separately"; hide the Startup health panel and Streamlit's Deploy menu (`.streamlit/config.toml`: `[client] toolbarMode = "viewer"`). Keep sources visible in reviewer mode | `app.py`, `features/review_questions.py` explanations | No internal names on learner screens; reviewer mode still shows provenance |
| A4 | Reviewer mode: "mark all right" shortcut; reviewer panels for due-review questions and the sample lesson | `app.py` `_render_review_panel`, `review.py` `review_targets` | A reviewer can judge every graded question type |
| A5 | Conversation: speaker name as a label (`田中さん:`); furigana over kanji only, not kana | `app.py` `_furigana_html` (use per-token readings from the toolkit) | ほかの人 shows furigana only over 人 |
| A6 | Lesson finish summary: what was practised, what was hard, when reviews come | `app.py` `render_learn` completion message | Summary lists items and next review date |
| A7 | Confidence: two submit buttons ("Sure", "Guessed") instead of a preselected radio plus Submit | `app.py` `_confidence_input` and submit buttons | Two clicks per question |
| A8 | First run: say what the app is on sign-in; no preselected role or tasks; generic task suggestions for a custom role; hide the disabled placement button; first-visit Home with one "Start your first lesson" | `app.py` auth, profile editor, `render_home`; `profile.py` `ROLE_TASK_SUGGESTIONS` | A new user is never told to "Continue" |
| A9 | Learn: explicit "Surprise me" button; examples of safe situations under the privacy warning | `app.py` `render_learn` | Surprise lessons do not rely on an empty box |
| A10 | Show times in Japan time and relative ("in 3 days"); "5 of 6 due" when the review is capped at 5 | `app.py` Home and review; reuse `core/history.LOCAL_OFFSET` | No UTC or past timestamps on learner screens |
| A11 | Hide Translate from navigation until it exists | `app.py` `PAGE_RENDERERS` | — |

## B. Phase 2 gate (people, not code)

Add the OpenAI keys; Siddhartha and the team use the app for about two weeks with reviewer mode on, fill the review sheet (`scripts/export_review_sheet.py`, `scripts/score_review_sheet.py`) and set the error-rate target. Review once: `resources/business_vocab_v1.json`, `jlpt_overrides_v1.json`, `milestones_v1.json` and the code-built review questions. Phase 3 starts when the error rate meets the target.

## C. Phase 3: personal learning

| ID | Task | Spec |
| --- | --- | --- |
| C1 | Personal word and grammar lists: add one at a time or paste many lines (`word, meaning`); S/A/B importance (consider a single "important for my job" star, UX risk R3); hide shared words; "not useful" | Decision 12. Table `personal_terms`; readings from the toolkit only; unmatched grammar is practice only; public-only note on the add boxes; limits 500 lines per paste, 2,000 per learner |
| C2 | Word priority and domain packs: code picks lesson target words by need score; broad packs (general office, engineering common, hardware, software, AI/ML, network, electronics lab, quantum, sales, marketing, management, other) | Decision 14. `priority = (0.4 D + 0.3 S + 0.2 C + 0.1 F) × g × (1 − m) × L`, computed per lesson. Pack words must exist in the dictionary; one start-up review, then learner signals (3 or more learners in a role add or reject a word). JMdict field tags and a local embedding model as sources. Microsoft 365 Copilot only as a manual paste-in source (a "copy Copilot prompt" button, UX risk R4) |
| C3 | Learning path: situation map per milestone (situation × who you talk to × channel × complication, coverage tracked), language tracks (grammar path, word sets, kanji readings, keigo forms, reading, writing and speaking), and a "Today" plan on Home | Decision 16. One "Start today" button: due reviews, then the track furthest behind with the reason shown, then free practice (UX risk R2). Writing, speaking and keigo nuance get AI feedback only (decision 6) |
| C4 | Milestone choice in the profile; S-graded words join the target set | Decision 13 |
| C5 | Progress for new learners: chosen milestone in stages of about 50 items, "at your pace" date, zero coverage rows behind "Show all" | UX fix 13, risk R5 |
| C6 | Short onboarding: ask role, level and goal at sign-up; ask domains and conversation partners later, in context | UX risk R1 |
| C7 | Presentation page: the two forms as two tabs | UX fix 15 |
| C8 | **Typed answers** (biggest learning gain): type the reading in kana, type the word from its English meaning, fill in a particle. New question forms next to multiple choice | Graded by code: exact match against `toolkit.readings()` and the lexicon forms (accept hiragana/katakana and listed spellings). New `QuestionForm` values and a migration for the `ck_attempt_question_form` check. Recall counts more than recognition in the policy (new policy version) |
| C9 | **Review in sentences**: due reviews show a new example sentence with the word blanked, not the word alone | Store one example sentence per item; only text the learner confirmed public (decision 2). Answer blanked by code; the answer must not appear elsewhere on screen |
| C10 | **Mix old into new**: each new lesson reuses 1–2 earlier words that are due | Part of word priority (C2): due items get a bonus in the need score; code checks they appear in the passage |
| C11 | **Explain wrong options and track confusions** (e.g. てもいい vs てはいけない) | Per-option explanations for code-built questions; a confusion count per pair from `review_attempts`; frequent pairs get a contrast drill |
| C12 | **Build the sentence**: put chunks in the right order | Part of the grammar track (C3); chunks from the tokenizer, order checked by code |

Done for Phase 3 when next-step picks make sense on real profiles of at least three different roles.

## D. Phase 4: multi-user runtime

FastAPI backend with Streamlit as a thin client (decision 4); PostgreSQL; a job worker for model calls; TTL storage for active sessions; per-user budgets and a usage view; replace the demo authentication (SSO later through an `IdentityProvider` port). Phone layout (UX fix 16). Done when a load test with 30 simulated users passes. Also: **short daily sessions** (5–10 minutes) with an optional reminder (e.g. Microsoft Teams) sent by the worker, so spacing works in practice.

## E. Phase 5: content bank and pilot

Placement test (bracketing staircase over code-verified items; needed before the pilot for a starting score). Milestone task checks: reading (code-verified keys, passed twice on different days), writing (code checks required words and grammar; AI feedback only), presentation (AI rubric feedback, learner confirms, optional senior sign-off via a link without an account, UX risk R6). Maintenance mode after the last milestone. **Listening**: a play button on each conversation line using text-to-speech (prefer an on-prem or local engine; lesson text is learner-derived, decision 2); not graded. **Use it this week**: the learner picks one phrase to use at work and confirms it the next day; feeds the can-do self-ratings. Eval suite in CI with a nightly run on the real model. Pilot metrics: recall at due reviews, 30-day retention, coverage growth per month, placement before and after, can-do self-ratings. Pilot with 20–30 users (decision 7; re-check the January 2027 date).

## F. Open items

- Translation page is a placeholder; decision 1 puts it in v1 scope.
- Mock mode has no fixtures for Explain mode, the deck localizer and delivery coaching (they fail safely).
- Check with IT that exporting Copilot word lists is allowed.
- Distractor quality in code-built review questions (UX fix 12), after the team review flags real cases.
