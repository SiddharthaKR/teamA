# Phase 3 Personal Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each learner a credible daily next step based on their chosen milestone, role, personal priorities, and saved learning evidence.

**Architecture:** Pure functions in `core/` choose targets and plan steps; services read user-scoped data and persist only approved records; the Streamlit app renders one daily route. The model writes lesson prose around code-selected targets, and existing validators decide which questions can be graded. Ship each slice with offline tests and a usable app.

**Tech Stack:** Python, Streamlit, SQLAlchemy/SQLite with Alembic, Pydantic, existing language toolkit and LLM gateway, pytest.

**Spec:** `docs/design/architecture-v2.md` (decisions 12–16), `docs/handoff/TASKS.md` (C1–C12), `docs/ux-review/README.md` (R1–R5). The team accuracy review is now a Phase 5 pre-pilot gate by user direction on 2026-10-28; initial packs still need review before use.

**Implementation note (2026-10-28):** Azure OpenAI routing, milestone choice, shorter setup, personal term preview/storage, quiz concealment, and separate-day policy are implemented on `v3`. Verified personal words become required targets in optional focused surprise lessons; missing targets reject the generated lesson. Focus defaults on every third completed lesson, with one rotating word per focused lesson. A draft versioned situation map now selects up to two dictionary-backed targets for recognized English scenarios using the existing content request. Domain/partner preferences, named review of the situation map, broader role packs, general-office fallback, due words outside the personal list, and the full three-role target check remain open. Tasks 3–9 and the three-profile exit gate remain open. No live Azure call or team review has run. See `docs/handoff/PHASE3_CONTINUATION.md` for the resume point.

**Today route slice (2026-10-28):** A draft three-step situation catalog per milestone, pure next-step selection, user-scoped Today service, and Home Start today navigation are implemented with TDD. Up to five due reviews precede the lesson and can be skipped. Completion of a real generated lesson with the exact suggested scenario advances the route; mock and fixture lessons do not. The broader Task 5 language tracks and Task 6 coverage, furthest-behind selection, and forecast are still open. The situation catalog awaits human relevance review.

**Word and first-track slice (2026-10-28):** Draft versioned general office, software, project management, and sales packs now feed blank lessons; one due reference word outside the personal list can join, and personal focus retains one slot. The situation map adds handover and customer follow-up, with contextual partner/domain ranking on recognized work prompts. Each milestone now has one word lesson route and offline grammar and phrase-order checks. Local checks record route completion only after an exact code-owned answer and do not change mastery. Catalog membership and examples await a named relevance review; see `docs/reviews/PHASE3_WORD_SETS.md`. Wider role packs, learner-signal overlays, preferred partner capture, and the remainder of Tasks 5–9 stay open.

## Global Constraints

- Phase 3 product work may begin now. A1–A11, especially quiz concealment and separate-day mastery, must be fixed before their affected learning and progress slices are accepted. The human accuracy review is a Phase 5 pre-pilot gate.
- `core/` has no UI, database, IO, or AI SDK imports. Prompt changes bump `PROMPT_VERSION` and snapshots. New modules and imports update the architecture graph.
- Only code-verified keys affect mastery. Unmatched personal grammar and ambiguous typed answers are practice. New mastery policy versions replay all old graded evidence.
- User-supplied terms sent to the model require the existing public-content confirmation. Persist parsed terms only. Do not persist learner prose or generated lesson sentences in `learning_items` or `review_attempts`.
- Every schema change has an Alembic migration and an upgrade test. All queries and mutations for personal terms, choices, and plans are scoped to the authenticated user.
- Existing `milestones_v1.json` remains the reference set. Personal S terms are additional targets shown separately; adding one must not silently change a fixed milestone denominator.
- Phase 5 owns placement and milestone task checks. Phase 3 may show coverage and progress, but must not call a milestone complete on coverage alone.

## Review Focus

1. An empty or unknown role/domain has a useful general-office target and a stated reason (Task 4 test).
2. All level-filtered or already-mastered candidates still yield an actionable due review or free-practice route (Task 6 test).
3. A homograph or multi-reading word is not wrongly graded against a single reading (Task 7 test).
4. An unconfirmed paste, duplicate, or over-limit batch cannot be sent to the model or saved by accident (Task 2 test).
5. A user cannot see another user's personal terms, priorities, or daily plan (Task 2 and Task 6 tests).

---

## Delivery order

| Checkpoint | Tasks | Usable result |
| --- | --- | --- |
| Entry | Current v3 baseline | Offline tests and a clean task baseline recorded |
| Personal targets | 1–4 | Chosen milestone, personal list, reviewed packs and validated word targets |
| Daily route | 5–6 | Returning learner starts a justified next lesson from Home |
| Deeper practice | 7–9 | Typed recall, contextual reviews, remaining tracks and contrast drills |
| Exit | Three-profile gate | Team signs off on complete daily loops |

Tasks 1 and 2 may proceed together. Task 3 needs named pack reviewers. Task 4 consumes Tasks 1–3; Task 6 consumes Tasks 4–5. Tasks 7–9 can follow once the daily route works.

## Baseline and learning integrity

- [ ] Record an offline baseline. Fix A1 (quiz concealment) and A2 (separate-day mastery, `t05-v2`) before accepting Tasks 6–7; add their specified tests and a live walkthrough.
- [ ] Complete A3–A11 alongside the relevant UI slices. Keep their acceptance checks in `docs/handoff/TASKS.md`.
- [ ] In Phase 5, set the team accuracy threshold before scoring, record review evidence, and pass the threshold before pilot recruitment.

## Task 1: Milestone choice and short setup (C4, C6)

**Files:** Modify `src/japanese_workplace_tutor/models.py`, `profile.py`, `core/learner.py`, `app.py`, `tests/test_profile.py`, `tests/test_app.py`; add an Alembic revision and `tests/test_migrations.py` case.

**Interface:** Persist `milestone_id` from `milestones_v1.json` and optional domain/partner preferences on the user profile. Existing profiles get a documented default or an explicit first-use choice; no account is blocked by migration. Expose the choice through `ProfileService`.

- [ ] Test a new learner selecting role, level and milestone, editing the choice later, and an existing profile after migration.
- [ ] Add the schema and service validation; ask for domains at the first word set and partners at the first situation, then render the short setup.
- [ ] Run focused profile, app and migration tests; check offline signup and restart manually; commit this slice.

## Task 2: Personal terms and priorities (C1)

**Files:** Create `src/japanese_workplace_tutor/personal_terms.py`; modify `models.py`, `app.py`, `core/difficulty.py`, `tests/test_migrations.py`; add `tests/test_personal_terms.py` and an Alembic revision.

**Interface:** A user-scoped `personal_terms` store with kind, expression, canonical reference ID where found, optional meaning, importance S/A/B, status and source. Parse one line or up to 500 pasted lines, at most 100 characters each and 2,000 active terms per learner. Preview each line before saving. Shared terms receive a user preference rather than a duplicate reference item; unknown words and grammar remain ungraded pending review.

- [ ] Test duplicate and canonical matching, unknown terms, privacy confirmation, paste limits, hide/not-useful actions, cascade deletion and cross-user isolation.
- [ ] Implement parsing and persistence; add a simple list screen with one-entry and bulk-preview flows. Ensure only parsed terms are stored and only confirmed public terms can become model targets.
- [ ] Run focused and migration tests; manually exercise a mixed paste and signout/signin; commit.

## Task 3: Reviewed domain packs (C2 prerequisite)

**Files:** Create versioned pack data under `src/japanese_workplace_tutor/resources/` and loader `core/domain_packs.py`; add `tests/test_domain_packs.py`, update `THIRD_PARTY_NOTICES.md` if sources change.

**Interface:** Start with general office plus at least three reviewed role/domain packs represented by real evaluation profiles. Every target has a dictionary/curated reference ID, provenance and pack version. Missing or unreviewed packs fall back to general office. Keep reviewed pack membership fixed and reproducible during the Phase 3 gate. Learner signals form a versioned priority overlay: three distinct learners in the same role can propose an add or demotion, and a single learner cannot vote three times. Record the signal separately from the reviewed base pack; no silent mutation of the source file.

- [ ] Test reference IDs resolve, duplicates collapse, unsupported roles fall back, and the three-distinct-learner signal threshold. Record the named human reviewer and source/version for each pack.
- [ ] Add reviewed data and loader. Treat embeddings and Copilot as candidate sources only; importing either is a separate decision after IT clearance and measured need.
- [ ] Run focused tests and an offline load; commit.

## Task 4: Deterministic word priority (C2, C10)

**Files:** Create `src/japanese_workplace_tutor/core/priority.py`; modify `features/lessons.py` and its prompt/schema only if required; add `tests/test_priority.py`, extend `tests/test_generation.py`.

**Interface:** `rank_targets(profile, candidates, progress, due, context) -> ranked targets with reason codes`. Implement the documented domain/situation/partner/frequency × importance × need × level score with fixed tie-breaking. A separate due-item lane can supply 1–2 eligible earlier words even when `mastery_score == 1`; it never changes SM-2 scheduling. A level filter with no candidates falls back to a safe in-level or general-office set and reports why.

- [ ] Test three real-role profiles, importance changes, already-mastered and due words, duplicate candidates, unknown roles and empty level-filtered sets.
- [ ] Have code choose 3–7 lesson targets (or the existing validated limit), pass them to generation, and check their actual appearance with the existing tokenizer/validators. A failed target check triggers the existing repair/fallback path, never a graded shortcut.
- [ ] Run priority and generation tests, then one mock-mode lesson per profile; commit.

## Task 5: Situation map and first language tracks (C3, C12)

**Files:** Create `core/learning_path.py` and versioned situation data under `resources/`; extend `lesson.py`, `features/lessons.py`, `app.py`; add `tests/test_learning_path.py` and lesson tests.

**Interface:** A milestone has a finite situation catalog and an ordered grammar path. Record coverage from completion metadata, not model prose. The first shipped tracks are situations, words and grammar; sentence-order exercises use curated chunk/order pairs with code-verified unique keys. The remaining tracks are Task 9, after the Today route exists.

- [ ] Test deterministic next situation, restart persistence, no duplicate coverage on retry, and a uniquely graded sentence-order question; ambiguous chunk permutations become practice.
- [ ] Implement one situation and one grammar route through the current lesson loop, plus a word-set route through Task 4 targets.
- [ ] Run focused tests and complete each route in mock mode; commit this working path.

## Task 6: Today plan and progress view (C3, C5)

**Files:** Create `src/japanese_workplace_tutor/today.py` as the service adapter; modify `core/learning_path.py`, `app.py`, `progress_view.py`; add `tests/test_today.py`, extend `tests/test_app.py` and `tests/test_progress_view.py`.

**Interface:** `build_today_plan(user_id, now) -> due step, next lesson, reason, optional free practice`. Due reviews come first but remain skippable. The next track is the furthest behind among eligible tracks for the chosen milestone, with a fixed tie-break and a human-readable reason. A single “Start today” action routes review, then lesson; show at most one alternative. Stage milestone coverage in roughly 50 reference items, with zero rows collapsed. Forecast dates require an observed pace and must say “not enough history” otherwise.

- [ ] Test empty history, missed days, all tracks exhausted, more than five due, skipped reviews, forecast with insufficient evidence and cross-user isolation.
- [ ] Implement the planner and Home/Progress rendering, with an honest coverage label rather than a premature milestone-complete claim.
- [ ] Run focused tests; walk through first day and returning day in mock mode; commit.

## Task 7: Typed recall and sentence reviews (C8, C9)

**Files:** Modify `core/items.py`, `core/progress.py`, `lesson.py`, `models.py`, `app.py`, `features/review_questions.py`; add `tests/test_typed_answers.py`, extend policy/history/migration tests and add an Alembic revision.

**Interface:** Add typed kana reading, word recall and particle forms. Normalize kana and whitespace, then grade only against a finite, code-owned set of accepted forms specific to the question's context. Multiple valid readings and meanings require a disambiguating prompt or practice-only status. Do not store raw typed answer text in `review_attempts`; retain correctness, form, source and time. Version the recall-weighted policy and replay historical evidence. Sentence reviews use curated public examples keyed by reference item and blank the answer in all rendered text; generated or learner-provided sentences stay session-only unless a separately reviewed retention policy is approved.

- [ ] Test valid variants, homographs, wrong but plausible forms, ambiguous particles, no answer leakage, no raw answer persistence, old-evidence replay and separate-day mastery.
- [ ] Implement typed submission and grading, policy/migration, then curated sentence review. Keep option-index submissions working for existing multiple-choice lessons.
- [ ] Run focused tests and complete both forms manually in mock mode; commit each working form.

## Task 8: Feedback, confusions, and presentation UX (C7, C11)

**Files:** Extend `features/review_questions.py`, `lesson.py`, `app.py`; add `tests/test_review_questions.py` and app tests.

**Interface:** Give per-option explanations only when supported by curated/code-owned evidence. Count confusion pairs from recorded option identifiers without retaining model prose. Show a contrast drill after a defined recurrence threshold (initial rule: two confusions across separate sessions); grade it only if its key is code-verified. Present the existing two presentation forms as tabs.

- [ ] Test two separate confusions, false positives, missing explanations, unverified contrast keys and unchanged practice-only behavior.
- [ ] Implement feedback and the two-tab UI; run focused tests and manual walkthrough; commit.

## Task 9: Complete the language tracks (C3)

**Files:** Extend `core/learning_path.py`, `features/lessons.py`, `app.py`, `tests/test_learning_path.py`, and feature tests; add a curated keigo-form resource and version it.

**Interface:** Kanji readings use dictionary-backed words and accept the reading in context. Keigo forms use a curated table for graded form recall; nuance receives feedback only. Longer reading has code-verified questions or practice-only questions. Writing and speaking are production practice with feedback only and no mastery update. Each track is eligible for Today only after it has a usable route and a coverage measure; otherwise it is labeled practice and excluded from “furthest behind” comparisons.

- [ ] Test contextual kanji readings, keigo variants, unverified reading questions, and no mastery change from writing/speaking practice.
- [ ] Build and verify one track at a time in mock mode; commit each independently usable route.
- [ ] Recheck Today eligibility and reasons after each added track; commit the final planner integration.

## Phase 3 exit gate

- [ ] Prepare at least three consented, real role profiles spanning distinct packs, with declared level, milestone and personal priorities. Record expected next-step choices *before* running the planner.
- [ ] For each profile, inspect the Today reason, target list and generated lesson; verify the chosen targets appear, keys are code-verified or explicitly practice-only, and a completed lesson changes the next day’s recommendation. Include an empty-profile and all-candidates-exhausted case.
- [ ] Run the project’s offline pytest suite, `python scripts/archmap.py check`, migration upgrade tests, and a mock-mode app walkthrough. Use the configured non-network model URL from `docs/handoff/TASKS.md`; never put credentials in the record.
- [ ] Log reviewer names, observed mismatches, corrections and the three-profile verdict in a Phase 3 verification record. Update `docs/handoff/PLAN.md` status only after the gate passes. A failed gate stays open with a specific fix owner.

## Decisions to settle before their dependent slice

- Name the accuracy target and reviewers before the Phase 5 pre-pilot review.
- Choose and review the first three role packs before Task 3; keep their provenance and version in the repository.
- Confirm with IT whether a manually pasted Copilot word list is allowed before presenting that path in the UI; ordinary manual entry does not depend on it.
- Decide whether public example sentences may be retained before extending C9 beyond curated, versioned examples. Session-only examples need no new retention decision.
