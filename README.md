# Japanese Workplace Learning

T07 provides a safe, local Streamlit application with persistent demo accounts, user-scoped learner profiles, validated generated scenario lessons, compact evidence-based mastery, and a skippable due-item review workflow.

## Overview (for evaluators)

Global employees in Japan can pass the JLPT yet struggle to operate in Japanese at work, and generic AI output is easily spotted as machine-written: wrong keigo, literal phrasing, and a slide flow that does not match Japanese norms. This app teaches workplace Japanese, lets learners rehearse real situations, and makes their Japanese read as a person wrote it.

### Capabilities
- Personalized lessons with evidence-based mastery and spaced repetition (the model proposes, the app decides; scoring is deterministic).
- Situation roleplay: practice a real workplace conversation, handle one curveball, and graduate when ready.
- Presentation localizer: turn an English deck into natural Japanese to paste, with the right register, a flow review, and per-slide speaker and nuance notes. Deck-type aware (technical, work status, business, casual/D&I, speech).
- Practice presenting: per-slide delivery coaching plus rehearsal with feedback.

### Architecture in one line
A Streamlit UI over a single generation service that routes each step to the model that is good at it (Tsuzumi for Japanese, a structured model for strict JSON), with tolerant parsing, per-phase fallback, and an always-ship fixture lesson so it never dead-ends.

### Reliability and privacy
Two-model fallback and schema validation keep generation working under failure; lessons, documents, and translations are ephemeral (only compact progress is stored); everything runs locally.

### Demo
See [`DEMO_GUIDE.md`](./DEMO_GUIDE.md). Sample input: `samples/demo_deck.pptx`; reference output: `samples/expected_output.md`. Keep `JLT_PRIMARY_MODEL=gpt-5-nano` for a fast demo.

## Code layout (v2)

Dependencies point inward toward a pure core; `lint-imports` (run by the test suite) fails the build if they do not.

| Package | Holds | May not import |
|---|---|---|
| `core/` | Domain types (items, questions, learner, inputs), Japanese script helpers, the progress policy `t05-v2` as pure functions with `replay()`, ports (`ModelTransport`, `DataClass`) | Anything with IO: Streamlit, SQLAlchemy, requests, or any outer package |
| `schemas/` | Pydantic contracts the model must satisfy | Features, the gateway, transports |
| `prompts/` | Versioned prompt builders (`PROMPT_VERSION` per feature), pinned byte for byte by `tests/test_prompts.py` | Features, the gateway, transports |
| `llm/` | `gateway.py`: the single path for model calls (routing, repair, fallback, hedging, PUBLIC/PRIVATE guard). `openai_transport.py`, `mock.py`: adapters | - |
| `features/` | Lessons, roleplay, presentation: orchestration and acceptance rules | Transports, Streamlit, SQLAlchemy |
| `generation.py` | `LessonGenerationService`, which composes the gateway and features; the stable import path for the app | - |
| `lesson.py`, `profile.py`, `models.py` | Persistence; the progress numbers come from `core/progress.py` | - |
| `app.py` | Streamlit UI and the composition root that picks a transport | - |

Every model task carries a `DataClass`. v1 tags all tasks `PUBLIC` (generic or user-attested content). The gateway refuses `PRIVATE` tasks unless the transport declares `accepts_private_data`, which only a future on-premises adapter will do.

## Trust layer (v2, Phase 2)

Japanese facts come from a local toolkit, not from the model:

- **Tokenizer:** SudachiPy with the core dictionary (dictionary forms and readings).
- **Levels:** OpenJLPT 0.1.0 (CC BY-SA 4.0) plus `resources/jlpt_overrides_v1.json`, which fixes known errors in that alpha dataset. A word not in the data shows as *unrated*; it never takes the model's guess.
- **Grammar:** `resources/grammar_points_v1.json`, 56 curated points whose levels still need team review.
- **Item IDs:** words map to their dictionary form, so 連絡します and 連絡 are one item. Grammar maps to the curated ID.
- **Answer keys:** a generated question is graded only when code confirms its key. A reading must be in the accepted readings, a meaning must match the reference glosses, and a cloze must reproduce a sentence from the passage with the blank hiding the target item. No distractor may also be right. Other questions stay as practice: their answers are logged with `is_graded = false` and never change mastery or schedules. A quiz needs at least 2 graded questions.
- **Difficulty:** every draft carries an 80/20 report (familiar, stretch and unrated words for the learner's level). A passage with more than 50% stretch words is regenerated.
- **Public content only:** typed scenarios and decks need a "public and non-confidential" checkbox, shown beside a do-not-upload-work-data note.
- **Roleplay and delivery practice (beta):** AI feedback only. Nothing is stored as pass/fail; the learner decides when they are ready.

### Team accuracy review (decision 9)

1. **Review sheet:** `python scripts/export_review_sheet.py --live --limit 20` writes `data/review-sheets/review_sheet.csv` from the golden set. Reviewers fill "Correct? (Y/N)". Then `python scripts/score_review_sheet.py data/review-sheets/review_sheet.csv --target 0.02` prints error rates by kind and by answer-key source.
2. **In-app reviewer mode:** set `JLT_REVIEWER_MODE=true`. Every lesson gets a panel to mark lines, items and questions right or wrong, and an **Accuracy** page reports the error rate.
3. **Normal use:** the team uses the app for a couple of weeks and reports problems informally.


- Windows with Python 3.14.3 (pinned in `.python-version`)
- A writable local checkout

## Clean setup

From PowerShell in the project root:

1. Create an isolated environment: `py -3.14 -m venv .venv`
2. Install locked direct and development dependencies: `.venv\Scripts\python -m pip install -r requirements-dev.txt`
3. Establish the migration baseline: `.venv\Scripts\python -m alembic upgrade head`

Model credentials are optional for fixture lessons and non-model features. To generate scenario lessons, copy `.env.example` to `.env` and provide the OpenAI-compatible endpoint, shared credential, primary Tsuzumi model ID, and fallback GPT model ID. Do not commit `.env`.

## Run

Start the app with one command:

`.venv\Scripts\python -m streamlit run app.py`

Open the URL shown by Streamlit. Register a local demo account without an email address, complete the required learner profile, then open Learn to generate a scenario lesson or complete the offline fixture lesson. Progress shows saved evidence. The startup health panel reports only:

- whether the database is ready;
- whether SQLite foreign-key enforcement is enabled; and
- whether all future model settings are present.

It never displays setting values. If model settings are absent, all non-model pages remain usable after sign-in.

## Demo authentication

- Usernames are Unicode NFKC-normalized and trimmed. Sign-in and uniqueness are case-insensitive, while the normalized display form is preserved.
- Usernames must be 3-64 characters and cannot contain control characters.
- Passwords must be 12-128 characters and are persisted only as Argon2id hashes.
- Accounts remain in SQLite after restart. Authentication is held only in Streamlit session state, so a lost session or application restart requires signing in again.
- This local mechanism is demo authentication, not enterprise identity. It has no shared/default credentials, email, recovery, SSO, or account lockout.

## Learner profile

- First sign-in requires a role or title, at least one typical task, and a self-reported level before protected navigation is available.
- Role and task suggestions are searchable, editable starting points. Custom roles and tasks are accepted.
- Technologies, tools, or business domain are optional. Romaji support defaults off.
- Profile values are isolated by account and remain in SQLite after sign-out or application restart.
- Declared level remains separate from the future estimated working level. Optional placement is displayed but unavailable until T15.

## Deterministic fixture lesson

- Learn contains one five-item workplace status-update lesson with meaning, reading, and contextual-cloze multiple-choice questions.
- Opening a lesson records exposure for each item but never raises mastery. Incorrect answers show immediate correction and schedule an alternate-form question for the same canonical item after the other first attempts.
- Each question submission is immutable and idempotent for its user and lesson session. Leaving an unfinished lesson retains already submitted compact evidence but writes no completion record.
- Progress shows user-scoped exposure, answer counts, overall mastery, latest outcome, SM-2 interval/ease, consecutive successful reviews, next-review timestamps, and the latest minimal completion metadata.
- Active passage, examples, questions, options, explanations, feedback, and recap exist only in Streamlit session state. SQLite stores canonical item IDs, compact answer evidence, schedule state, and topic/difficulty/item-ID completion metadata. Refresh/process loss removes active content and requires sign-in again.

## Due-item review

- Home shows a draft route for the learner's chosen milestone. **Start today** opens up to five due reviews first (skippable), then the suggested step on Learn. Each milestone currently has three situations, one word lesson, one local grammar check, and one local phrase-order check. Home offers one offline practice alternative when a local step is waiting. Correct local answers advance their steps without changing mastery. Completed generated lessons advance situation and word routes using a stored topic ID; repeating a step counts once. Offline sample lessons do not advance generated routes.
- Home queries the signed-in learner's persisted schedules. When items are due, **Review due items** is the primary action and shows the total due count; **Start a lesson** remains available.
- A review contains at most five items ordered by earliest due date, lowest mastery, then canonical ID. The deterministic question targets the weakest available evidence dimension.
- Starting or skipping a review does not change progress. Only submitted graded answers update compact evidence, mastery, and SM-2 schedules through policy `t05-v2`.
- Each submission is idempotent for the user, review session, and question. Immediate feedback shows the mapped outcome and new review date.
- Completing a review returns Home, reports the result, shows the earliest remaining review schedule, and refreshes the due count. Review prompts and feedback remain session-only and are not stored in SQLite.

## Generated scenario lessons

- Learn accepts an optional workplace situation or goal, or Japanese text up to 4,000 characters. English defaults to **Generate a lesson from this scenario** and Japanese defaults to **Explain this Japanese text**; the learner confirms or changes the mode before generation. A blank Generate-mode request creates a varied surprise workplace lesson and avoids recently completed topic IDs.
- For a blank Generate-mode request, a checkbox can focus the lesson on one verified, level-appropriate word from the learner's public personal list. It defaults on for the first and every third completed lesson; the learner can override it. Words rotate by exposure, and mastered words wait until due. The generator must use and explain the selected word or the lesson is rejected. Explicit scenarios and Explain mode keep their original subject and text. Mock fixtures may not contain arbitrary personal words, so personalized generation needs a configured model.
- For a typed English scenario that matches a versioned workplace situation, local code selects up to two dictionary-backed words at an appropriate level. These join the existing content prompt as one target list, with no extra model call. The same dialogue-and-explanation check applies. Unknown situations have no forced words; Explain mode is untouched. The situation mapping is a draft awaiting human relevance review, and mock fixtures do not apply these dynamic targets.
- The situation map also covers handovers and explicit customer follow-ups. For recognized workplace situations, the named conversation partner and learner role/domain can change word ranking. Blank surprise lessons choose from draft general office, software, project management, or sales packs and may include a due reference word outside the personal list. A personal-focus lesson keeps one personal word and leaves one slot for a due or pack word. The packs and situation membership await named relevance review; every selected expression is checked against `business-v1` and the learner's level.
- Mixed prompts about a party, weekend, or social event do not force workplace-set words even if they mention a meeting or status update. The AI-led content request handles those prompts. This guard is intentionally narrow; other ambiguous topics may still need evaluation.
- For scenario generation, the scenario's technical, general, or social subject outranks the learner's role and tasks. Role data adjusts relationships, register, and difficulty without injecting technical content into a general or social situation. Generated passages are actual multi-turn, speaker-labelled workplace conversations rather than lesson descriptions.
- Explain mode preserves the supplied Japanese text exactly. It cannot rewrite, correct, extend, or add Japanese sentences, and target-item examples must reuse exact source lines.
- Every generated passage line has a visible line-by-line English meaning plus structured kanji, vocabulary, and grammar explanations. The content response must pass a strict Pydantic schema requiring complete ordered line coverage and 3-7 Japanese target items drawn from those explanations before anything renders.
- Quizzes test Japanese kanji, vocabulary, and grammar used in the passage, never English words merely present in it. The prompt includes compact prior item evidence and the learner's working JLPT level so weak items can be reinforced, mastered items are not over-tested, and stretch content remains supported.
- The application treats scenario text as untrusted content and sends the learner profile, compact learning evidence, and recent topic IDs separately.
- Lesson content renders as soon as it validates. A separate in-memory background job immediately prepares 4-6 grounded questions and their varied retries while the learner studies. **Go to quiz** reveals and activates the quiz only after the learner chooses it; a failed quiz job leaves the lesson available for retry.
- Each phase calls the configured Tsuzumi route and falls back to GPT. Schema-validation failures receive one same-model repair; technical failures skip the redundant Tsuzumi repair and fall back immediately. HTTP connections are pooled across the content and quiz requests.
- GPT-5 requests use low reasoning effort and strict JSON Schema output. Collection bounds and exact four-option requirements are represented directly in the provider schema; repair feedback is capped to avoid oversized retry prompts.
- The UI separately displays **Lesson generated with Tsuzumi 2/GPT-5 nano** and **Quiz generated with Tsuzumi 2/GPT-5 nano**, based on the successful route for each phase. Model IDs, endpoints, credentials, prompts, responses, and failure details are not shown.
- Full lesson responses can take longer than short health probes, especially when every line is explained. `JLT_MODEL_TIMEOUT_SECONDS` defaults to 180 seconds and can be adjusted for the configured proxy without changing provider code.
- Opening validated content records exposure once. Promoting its validated quiz does not record exposure again, and answers use the same application-owned scoring, corrective retry, mastery, SM-2, idempotency, and minimal completion-metadata path as the fixture lesson. Model output cannot set progress or schedules.
- Generated passage, examples, prompts, options, explanations, feedback, recap, and scenario text remain in Streamlit session state only. Total provider failure preserves the scenario for retry and creates no exposure or progress rows.

### Mastery policy `t05-v2`

- Evidence dimensions are recognition, reading, contextual use, and grammar application. Full question text and feedback are never persisted.
- `Again` is an incorrect answer: mastery changes by `-0.08` to a floor of `0`, ease drops by `0.20`, the interval resets to `0`, and review is due in 10 minutes.
- `Hard` is a correct alternate-form retry after failure: mastery changes by `+0.08`, ease drops by `0.15`, and review is due in one day. The original `Again` row remains immutable.
- `Good` is a first-try success: mastery changes by `+0.18`, ease rises by `0.05`, and intervals progress from 1 day to 3 days, then multiply by ease.
- `Easy` changes mastery by `+0.30`, raises ease by `0.15`, and multiplies a minimum 4-day interval by ease and `1.3`. It requires at least two preceding consecutive first-try successes on separate Japan calendar days and successful evidence from at least two question forms.
- Mastery is `0.80`. Non-Easy evidence and evidence from only one form are capped at `0.79`, so one response, one session, or repeated same-form guesses cannot master an item.

Golden vectors from an initial ease of `2.50`: `Again` gives mastery/ease/interval `0.00/2.30/0`; recovery `Hard` gives `0.08/2.15/1`. Two later `Good` sessions followed by two eligible `Easy` sessions produce mastery `0.08 → 0.26 → 0.44 → 0.74 → 1.00`, ease `2.15 → 2.20 → 2.25 → 2.40 → 2.55`, and intervals `1 → 3 → 7 → 22 → 73` days.

## Test

Run all lesson, profile, authentication, startup, navigation, migration, retention, configuration, database, and secret checks:

`.venv\Scripts\python -m pytest`

Run only the repository secret scan:

`.venv\Scripts\python -m pytest tests/test_secret_scan.py`

The scan includes notebook source/output JSON. Before sharing, also inspect version-control history with an approved secret-scanning tool because deleting a credential from the current tree does not remove historical commits.

## Configuration

All settings use the `JLT_` environment prefix:

| Variable | Required now | Purpose |
|---|---:|---|
| `JLT_DATABASE_URL` | No | SQLAlchemy URL; defaults to `sqlite:///data/app.db` |
| `JLT_MODEL_BASE_URL` | For generation | OpenAI-compatible base URL; for Azure v1, `https://<resource>.openai.azure.com/openai/v1` |
| `JLT_MODEL_API_KEY` | For generation | Shared model credential |
| `JLT_MODEL_PROVIDER` | No | `openai-compatible` (default) or `azure`; Azure sends the key in the `api-key` header |
| `JLT_AZURE_API_VERSION` | Azure deployment route only | Leave unset for Azure v1; set a supported version when using the Azure resource root URL |
| `JLT_PRIMARY_MODEL` | For generation | Primary Tsuzumi model ID |
| `JLT_FALLBACK_MODEL` | For generation | Fallback GPT model ID |
| `JLT_MODEL_TIMEOUT_SECONDS` | No | Per-attempt provider timeout; defaults to 180 seconds |
| `JLT_LLM_MODE` | No | `live` (default), `mock` (offline fixtures, no keys needed) or `record` (live calls appended to a JSONL file) |
| `JLT_MOCK_FIXTURE_DIR` | No | Fixture folder for mock mode; defaults to `fixtures/llm` |
| `JLT_LLM_RECORDING_PATH` | No | JSONL output for record mode; defaults to `data/llm-recordings/recordings.jsonl` |

Model status is configured only when all four model variables are present. Scenario generation is disabled when any value is absent; all offline features remain available.

### Offline mock mode (v2, Phase 0)

Set `JLT_LLM_MODE=mock` to run the full learning loop without any model credentials. `MockTransport` replays the hand-checked fixtures in `fixtures/llm/` through the real prompts, validators and fallback policy, so tests and demos exercise the same code paths as production. Rebuild the fixtures with `python scripts/build_mock_fixtures.py`; a test fails if the committed files drift from the builder. Mock mode covers surprise and scenario lessons, quizzes and roleplay; Explain mode and the deck localizer have no fixtures yet and fail safely with the normal error message.

`JLT_LLM_MODE=record` calls the live endpoint and appends every prompt and response to `JLT_LLM_RECORDING_PATH`. Record only PUBLIC inputs such as the golden set in `evals/golden/v0.json`, never learner-supplied private text.

## Database and migrations

SQLite files are local and ignored by Git. Every application-created SQLite connection executes `PRAGMA foreign_keys=ON`. Alembic owns the schema, including T02 accounts, T03 learner profiles, T04 learning records, and T05 dimension/mastery/SM-2 evidence. Run the upgrade command after pulling schema changes and before starting the app.

Useful migration checks:

- Upgrade: `.venv\Scripts\python -m alembic upgrade head`
- Current revision: `.venv\Scripts\python -m alembic current`
- Downgrade baseline: `.venv\Scripts\python -m alembic downgrade base`

## Credential incident action

A prototype credential was removed from the notebook. The credential must still be treated as compromised: its owner must revoke or rotate it in the provider console and clean any version-control history or shared copies containing it. This external action cannot be verified by the application and remains a T01 release blocker until the owner records confirmation.
