# Product Requirements Document

> **Version 2 (post-hackathon), updated 2026-10-25.** Sections 1–18 below are the hackathon PRD (tasks T01–T18) and stay the baseline. Section 0 records what changed when the project became an internal NTT-AT tool. Where they disagree, section 0 wins. Design details: `docs/design/architecture-v2.md` (decisions 1–16); plan for team review: `docs/handoff/PLAN.md`; task list: `docs/handoff/TASKS.md`; UX walkthrough: `docs/ux-review/README.md`.

## 0. Version 2 update (post-hackathon)

### Context
- The hackathon app won 3rd prize and continues as an internal NTT-AT tool on an on-prem server.
- Model provider: OpenAI API (keys pending; mock mode for development and tests). An on-prem model may come later.
- Pilot: 20–30 users from 2–3 teams for about 3 months; target around January 2027, to re-check against the longer phase plan.
- No regular Japanese reviewers: Siddhartha and the team review accuracy once or twice, not monthly.

### Vision (v2)
Each learner reaches a workplace goal they choose: they can read, write and present the Japanese their own job needs. Lessons follow their role, domains, situations and the people they talk to, and the app shows honestly how far they have come.

### Product principles added in v2
- **The model proposes; the code decides.** Anything graded, stored as fact or shown as authoritative comes from curated data or a code check. JLPT levels, readings and answer keys never come straight from the model.
- **Trust before scale.** The team accuracy review (Phase 2 gate) comes before multi-user and the pilot.
- **Privacy.** Only content the learner confirms is public goes to OpenAI (checkbox plus warning). Private work documents are not sent. Every prompt task is tagged PUBLIC or PRIVATE.
- **Progress is replayed from evidence.** Answers are stored once and never changed; mastery comes from a versioned policy, so the rules can change and old answers are re-scored.
- **Honest progress.** No streaks or points; measure recall after a gap.

### Goals (v2)
1. Trustworthy content: dictionary-based readings and levels, code-checked answer keys, a difficulty check (most words at the learner's level or Business Japanese).
2. A clear end goal: three milestones (Get by ~A2, Take part ~B1, Contribute ~B2), each done at 80% word and grammar coverage plus reading, writing and presentation checks; then maintenance.
3. Visible progress: item status, coverage per word list, milestone bars and progress over time.
4. Personal learning: personal word lists, word priority by role and domain packs, a learning path with a daily plan.
5. Stronger memory: typed answers graded by code, reviews in sentences, mixing old words into new lessons.

### Non-goals (v2)
- Audio, listening assessment, pronunciation and speech recognition (listening via text-to-speech is planned in Phase 5, ungraded).
- Sending private or confidential work documents to OpenAI. Document upload is on hold.
- Stored pass/fail from the AI for roleplay, writing or presentations: feedback only.
- Direct Microsoft 365 Copilot integration during the pilot (learners may paste a Copilot word list by hand).
- Enterprise SSO before Phase 4.

### Personalisation (v2)
- Profile: role, tasks, domains (several allowed), level, chosen milestone; usual conversation partners later.
- Word priority: code picks each lesson's target words by a need score, priority = (0.4·domain + 0.3·situation + 0.2·who you talk to + 0.1·frequency) × importance grade × (1 − mastery) × level filter. Computed per lesson, never stored per user.
- Domain packs: general office, engineering common, hardware/electronics, software, AI/ML, network, electronics lab, quantum, sales, marketing, management, other.
- Personal lists: add words or grammar one at a time or by pasting lines; mark importance; hide shared words; "not useful". Words several learners in a role add or reject change that role's pack automatically.

### Learning (v2)
- Learning path: a situation map per milestone (situation × who you talk to × channel × complication), language tracks (grammar, word sets, kanji readings, keigo, reading, writing and speaking), and a daily "Today" plan: due reviews, then the step furthest behind with its reason, then free practice.
- Quiz: the lesson is hidden while answering; typed answers (kana readings, words from meanings, particles) join multiple choice; wrong options are explained; confusion pairs get contrast drills.
- Writing and speaking: typed practice in roleplay and presentation practice (feedback only). No audio.

### Phases
| Phase | Goal | Exit gate |
| --- | --- | --- |
| 0 Baseline (done) | Tag the hackathon build, mock mode, golden set | Tests pass offline |
| 1 Split the core (done) | Core rules separate from UI and AI | No feature imports an AI SDK |
| 2 Trust layer (built) | Nothing graded comes unchecked from the AI | Team accuracy review below an error-rate target |
| 3 Personal learning | Lessons fit each person's job and goal | Next-step picks make sense for at least three roles |
| 4 Multi-user runtime | Many users on the on-prem server | Load test with 30 simulated users |
| 5 Content bank and pilot | Placement, milestone checks, pilot | Pilot review: flag rate, cost per lesson, retention |

### Pilot success measures
Recall rate at due reviews, 30-day retention, coverage growth per month, placement score before and after, can-do self-ratings.

### Superseded hackathon requirements
| Section | Hackathon rule | v2 rule |
| --- | --- | --- |
| 1 Primary MVP outcome | A 10-minute demo of the learning loop | The milestone end goal and pilot measures above |
| 6 Placement | Optional placement | Required before the pilot (Phase 5) for a starting score |
| 8 Document learning | Ephemeral document lessons | On hold: private documents may not go to OpenAI |
| 9 Question types | Multiple choice only; no typed answers | Typed answers graded by code are planned (Phase 3). A question is graded only when code verifies its key; otherwise it is practice |
| 9 Guessing protection | Success across forms and separate reviews | Success across forms on separate **days** (current code counts separate sessions; fix planned before the team review) |
| 10 JLPT reference strategy | JLPT lists, else model judgment | tanos JLPT lists, OpenJLPT only for gaps, curated overrides, a Business Japanese list; a word on several levels counts at its easiest; levels never from the model |
| 10 Persisted history | No lesson text stored | Item names are stored (reference-list spelling only, never learner text) for the progress page and due reviews |
| 11 Translation | In MVP scope | Still in v1 scope; not built yet |
| 12 Progress dashboard | Mastery and weaknesses | Status, coverage per list, milestones, progress over time, This week card on Home |
| 14 Authentication | Local demo accounts | Kept until Phase 4; real login then |

## 1. Product Summary

### Working title
TBD

### Product vision
A personalized Japanese learning assistant for global employees working in Japanese environments. The product teaches language relevant to each learner’s role, tasks, and workplace situations while adapting to their declared level and demonstrated mastery.

### Primary target audience
Global employees who work in Japanese environments across user-selectable roles.

### Primary MVP outcome
Demonstrate a complete personalized learning loop in under 10 minutes:

1. The learner creates a profile and declares a Japanese level.
2. The learner receives a role- and level-adapted lesson.
3. The learner studies and completes a short quiz.
4. The application updates and persists item-level mastery and review schedules.
5. A subsequent lesson visibly adapts to the learner’s saved progress.

### Secondary quality indicators
- Lesson content matches the learner’s role and approximate JLPT level.
- Document explanations are grounded in selected source spans.
- Quiz results update progress correctly.
- Progress remains available after restarting the application.

## 2. Goals and Non-Goals

### Goals
- Personalize Japanese lessons using role, typical tasks, optional tools/domain, level, and learning history.
- Support generated lessons, user-supplied scenarios, and ephemeral Japanese workplace documents.
- Teach kanji, vocabulary, grammar, and workplace usage through a repeatable learning loop.
- Provide level-adaptive English-to-Japanese workplace translation.
- Persist structured mastery and spaced-repetition state without retaining sensitive lesson, document, or translation content.
- Make progress deterministic and explainable rather than allowing the LLM to invent it.

### MVP non-goals
- Official or certified JLPT assessment.
- Comprehensive support for every role through manually curated role packs.
- Audio, listening, pronunciation, or speech assessment.
- Scanned-document OCR.
- Persistent document, lesson-content, or translation history.
- Enterprise SSO or Microsoft Entra ID.
- Gamification, points, badges, streaks, or leaderboards.
- Human approval of every generated lesson.
- Public hosting; the primary demonstration target is a local laptop.

## 3. Product Principles

1. **Work relevance:** Lessons should reflect the learner’s role and typical tasks.
2. **Comprehensible challenge:** Approximately 80% of lesson language should be familiar or at the current level and 20% should be supported stretch content.
3. **Evidence-based progress:** Exposure alone does not increase mastery; answered questions provide mastery evidence.
4. **Privacy by default:** Uploaded documents, lesson content, and translations are ephemeral.
5. **Grounded explanations:** Document-derived explanations point to source spans.
6. **Natural and learnable output:** Translation provides both professionally natural Japanese and a learner-accessible version.
7. **Structured generation:** LLM responses use feature-specific JSON schemas and application validation.

## 4. User Experience and Navigation

### Top-level pages
- **Home**
- **Learn**
- **Translate**
- **Progress**
- **Profile**

### Home
When reviews are due, the primary action is **Review due items**. It starts a short review of up to five items. Starting a new lesson remains available and is never blocked.

When no reviews are due, the primary action is **Continue learning** or **Start a lesson**.

### Interface language
- English UI and explanations by default.
- Japanese lesson and translation content.
- Adaptive furigana for unfamiliar kanji.
- Romaji is optional and hidden by default, except that complete beginners may enable it.

## 5. Onboarding and Learner Profile

### Required fields
- Role/title
- Typical tasks
- Self-reported Japanese level

### Optional fields
- Technologies, tools, or business domain
- Project-specific context supplied later through a scenario or ephemeral document

### Role input
- Provide searchable suggestions for common roles.
- Allow unrestricted free-text roles.
- Suggest typical task chips based on the role.
- Allow users to edit or add tasks.

### Level options
- Complete beginner
- JLPT N5 through N1
- Unsure

### Level model
Store level information separately:

- **Declared level:** The learner’s self-reported level. The learner may change it at any time.
- **Estimated working level:** A cautious estimate informed by optional placement and later performance.
- **Level source/confidence:** Identifies whether a level is self-reported, placement-estimated, or performance-estimated and records confidence.

A broad self-reported level controls initial difficulty but does not mark individual language items as mastered.

## 6. Optional Adaptive Placement

### Experience
- Placement is optional.
- Use 10–15 adaptive multiple-choice questions.
- Cover vocabulary, kanji, grammar, and reading.
- Questions are generated by the LLM rather than selected from a curated item bank.
- Generated answer keys are trusted for scoring.
- Output must still pass structural schema validation so the UI can render it safely.

### Authority and limitations
- Placement is explicitly an unverified estimate, not an official JLPT result.
- The result is shown as a recommendation.
- The learner chooses whether to accept it as the estimated working level.
- The learner may ignore or retake placement.
- Placement never overwrites the declared level.

### Progress impact
- Placement answers may create low-confidence provisional item evidence.
- Placement success must not immediately mark an item as mastered.
- Later varied success in lessons and reviews is required.
- Persist compact skill/item evidence rather than complete generated question text.

## 7. Learn Workflow

### Lesson entry points
The Learn page supports:

1. A generated personalized lesson.
2. An optional English or Japanese scenario/string.
3. A TXT or text-based PDF upload.
4. A file plus scenario, where the file is authoritative and the scenario specifies the desired focus.

If neither a scenario nor a document is supplied, generate a personalized “surprise me” lesson.

### Scenario behavior
- Accept a short situation, goal, or text in English or Japanese.
- Detect the likely intent and show an explicit mode:
  - Generate a lesson from this scenario.
  - Explain this Japanese text.
- If combined with a document, use the scenario only to select and frame relevant document content.
- Clearly label general teaching examples that do not come from the document.

### Random lesson selection
“Random” means personalized surprise rather than uniform randomness. Topic selection is weighted using:

- Role and typical tasks
- Weak skills
- Due review items
- Unseen workplace situations
- Recently used topic IDs, to reduce repetition

The application selects a topic brief deterministically; the model generates content within that brief.

### Standard lesson length
- Approximately 5–8 minutes
- A short workplace passage or scenario
- 3–7 target learning items
- 4–6 quiz questions

### Standard lesson structure
1. Explain the passage or workplace situation.
2. Introduce selected kanji, vocabulary, and grammar.
3. Show workplace examples and usage guidance.
4. Provide selective inline annotations.
5. Run short recognition and contextual-cloze practice.
6. Explain mistakes and perform delayed varied retries.
7. Recap learned items and update progress.

### Inline annotations
- Annotate only unfamiliar, near-level, and stretch items.
- Known/mastered items remain unannotated unless help is requested.
- Revealing an annotation shows, as applicable:
  - Reading
  - Meaning
  - Grammar explanation
  - Workplace nuance
  - Furigana
  - Optional romaji
- Document annotations point to source spans.

### Difficulty adaptation
- Target approximately 80% current/known content and 20% next-level stretch content.
- Provide support for every stretch item.
- Adapt using both the estimated working level and item mastery.
- JLPT is a guide rather than an absolute statement of workplace difficulty.

## 8. Document Learning

### Supported inputs
- Pasted Japanese or mixed Japanese-English text
- TXT files
- Text-based PDF files

English-only scenario descriptions use the scenario-generation path rather than being presented as Japanese document explanation.

### Limits
- Maximum 10 PDF pages or 50 KB of extracted text.
- Reject encrypted PDFs.
- Reject scanned/image-only PDFs in the MVP and explain that OCR is unsupported.

### Passage selection
For a multi-page document:

1. Extract headings and candidate chunks.
2. Suggest 2–4 useful sections with short previews.
3. Let the learner confirm the section.
4. Generate a lesson only from the selected source span and any clearly labeled general examples.

### Grounding
- Each source-based explanation and annotation links to a highlighted source span.
- Source span offsets are retained only during the active session.
- Unsupported additions are labeled as general language guidance.

### Privacy and lifecycle
- Process documents ephemerally.
- Do not retain original files or extracted source text after the active session.
- Warn users not to upload confidential information.
- An unfinished lesson remains in session state only and is discarded on expiry or logout.
- Warn before navigation if leaving would discard an unfinished lesson.
- Mastery changes only from completed interactions, not from displaying content.

### Deferred security decision
The detailed prompt-injection handling policy was skipped during planning and must be resolved before accepting untrusted uploads. At minimum, uploaded text must be treated as data rather than application instructions, and schema/source-span validation must remain enforced.

## 9. Quiz and Feedback Behavior

### Question types
- Multiple-choice meaning recognition
- Multiple-choice reading recognition
- Multiple-choice contextual cloze
- No typed-answer or sentence-production questions in the MVP

### Incorrect answer behavior
1. Show immediate corrective feedback and the correct answer.
2. Explain why the selected answer was incorrect.
3. Ask a different question testing the same concept later in the lesson or review.
4. Count the first attempt as the initial evidence.
5. Record delayed-retry success as recovery evidence rather than replacing the first result.

### Guessing protection
- A single correct multiple-choice answer never marks an item mastered.
- Require success across different question forms and separate reviews.
- Use historical evidence before assigning the strongest review outcome.

## 10. Progress and Spaced Repetition

### Tracked item categories
- Kanji
- Vocabulary
- Grammar

### Item-level model
Each learning item has:

- Canonical identifier and text
- Item category
- JLPT reference level when available
- Level provenance: JLPT reference or model estimate
- Confidence for model-estimated levels
- Overall mastery score from 0–100
- Skill dimensions, such as recognition, reading, contextual use, and grammar application where applicable
- Exposure count
- Correct and incorrect attempt counts
- Consecutive successful reviews
- Last reviewed timestamp
- Next review timestamp
- SM-2 interval and ease values

The UI emphasizes a simple overall mastery value while internal dimensions guide question selection.

### JLPT reference strategy
- Use JLPT lists when the item is available in the project’s reference data.
- Use model judgment when JLPT data is insufficient.
- Store provenance and confidence for model-estimated levels.
- Do not use uncertain labels as strict inclusion/exclusion gates.
- Keep provenance mostly internal unless confidence is low or the learner requests details.

### Review algorithm
Use simplified SM-2 with automatic evidence mapping:

- Incorrect first attempt → **Again**
- Correct after prior failure → **Hard**
- First-try success across varied evidence → **Good**
- Repeated first-try success across reviews → **Easy**

“Easy” cannot be earned from a single response.

### Review experience
- Offer up to five due items before a new lesson.
- Reviews are skippable and never block new learning.
- Reuse one or two due items in a new lesson when contextually natural.

### Mastery rules
- Displaying an item is exposure and does not increase mastery.
- Translation usage does not increase mastery.
- Completed objective quiz/review answers update mastery.
- Placement evidence is provisional and lower confidence.
- Repeated, varied success is required for mastery.

### Persisted history
Do not store replayable lesson history. Persist only:

- Item progress and scheduling records
- Quiz/review evidence needed to update mastery
- Minimal completed-lesson metadata:
  - Topic/category ID
  - Difficulty
  - Studied item IDs
  - Completion timestamp

Do not persist generated lesson text, document excerpts, or full question text.

## 11. Translation Workflow

### Input
- English workplace sentence or passage
- Required context:
  - Audience relationship: manager, peer, subordinate, customer, or unknown
  - Communication channel: email, chat, meeting, document, or presentation
  - Intent and tone: request, update, apology, disagreement, urgency, and desired tone

If a context value is absent, use and visibly display a default assumption rather than silently guessing.

### Output
Provide two clearly labeled versions:

1. **Natural workplace Japanese:** Professionally appropriate Japanese that preserves intent and required politeness.
2. **Learning version:** A simpler version adapted to the learner’s current level and known items.

Also explain:

- Differences between the two versions
- Unfamiliar vocabulary or grammar introduced by the natural version
- Register, politeness, and workplace nuance
- Adaptive furigana and optional romaji

Never simplify required politeness or alter the intended meaning merely to remain within known vocabulary.

### Progress and retention
- Translation creates session-only exposure and no automatic mastery gain.
- The MVP does not persist English input or Japanese output.
- There is no translation history.

## 12. Progress Dashboard

The Progress page prioritizes:

- Due reviews and the next review action
- Mastery by kanji, vocabulary, and grammar
- Skill-dimension weaknesses where useful
- Recent improvement
- Declared level versus estimated working level

Do not claim an exact JLPT completion percentage when mappings are incomplete or model-estimated.

No gamification is included.

## 13. Profile and Data Controls

The Profile page allows users to:

- Edit role/title
- Edit typical tasks
- Edit optional technologies/tools/domain
- Change declared Japanese level at any time
- Enable or disable romaji
- Start or retake optional placement
- Accept or ignore a placement recommendation
- Reset all learning progress
- Delete the complete demo profile and associated records

Reset and deletion require confirmation.

## 14. Authentication and Persistence

### Authentication
- Lightweight local username and password.
- Store passwords using a modern password hash such as Argon2 or bcrypt.
- Do not collect email addresses.
- Do not provide default shared credentials.
- Label the mechanism as demo authentication rather than enterprise-grade identity.

### Database
- SQLite for the hackathon MVP.
- SQLAlchemy for persistence and migration flexibility.
- Enable SQLite foreign-key enforcement.
- Keep identity boundaries clean enough to migrate to Entra ID and Postgres later.

### Suggested core entities
- `User`
- `LearnerProfile`
- `LearningItem`
- `UserItemProgress`
- `ReviewAttempt`
- `PlacementSummary`
- `CompletedLessonMetadata`

## 15. LLM and Application Architecture

### Model strategy
- Primary model: **Tsuzumi 2**
- Fallback model: **GPT-5 mini**
- Hide model selection from learners.

### Fallback policy
1. Call Tsuzumi 2.
2. If a timeout, provider error, malformed schema, or failed source-span validation occurs, retry/repair with Tsuzumi 2 once.
3. If the technical or validation failure remains, call GPT-5 mini.
4. Do not fall back merely because an answer appears stylistically weak.
5. Log the selected model and fallback reason without exposing implementation details in normal UI.

### Structured output
- Use strict feature-specific JSON schemas for placement, lessons, annotations, quizzes, source spans, and translations.
- Validate all responses before rendering.
- Retry malformed responses according to the fallback policy.
- Never let the model directly update persisted mastery, authentication, authorization, or review schedules.
- Calculate scoring and SM-2 scheduling in deterministic application code.

### Failure experience
If both models fail:

- Show a concise, safe error.
- Preserve typed scenario/form input in the active session.
- Keep extracted file content only until session expiry.
- Offer a retry.
- Never display or score partial invalid output.
- Never update progress from a failed generation.

## 16. Technical Stack and Deployment

### MVP stack
- Python
- Streamlit
- Pydantic for structured response validation
- SQLAlchemy
- SQLite
- OpenAI-compatible client for the configured model proxy

### Deployment target
- Local laptop demonstration
- Seeded or easily created demo profiles
- A reliable reset flow between demonstrations
- A documented future path to hosted deployment, persistent managed storage, enterprise identity, and secure secret management

### Secret management requirement
No API key may be embedded in source files or notebooks. The currently embedded credential in the prototype notebook must be revoked/rotated and replaced with environment-based configuration before further development or sharing.

## 17. Data Retention Summary

| Data | Persisted? | Notes |
|---|---:|---|
| Username and password hash | Yes | No email required |
| Learner role, tasks, optional domain/tools | Yes | Editable by user |
| Declared and estimated level | Yes | Store source/confidence |
| Item mastery and SM-2 state | Yes | Core personalization data |
| Compact placement evidence | Yes | Provisional, no full question text |
| Minimal lesson metadata | Yes | Topic, difficulty, item IDs, timestamp |
| Original uploaded files | No | Session-only |
| Extracted document text | No | Session-only |
| Generated lesson content | No | Session-only |
| Full quiz question text | No | Session-only |
| English translation input | No | Session-only |
| Japanese translation output | No | Session-only |
| Per-item product feedback | No | Feedback controls removed from MVP |

## 18. MVP Acceptance Criteria

A demonstration is successful when:

1. A new user can create a local account and complete onboarding.
2. The user can choose a suggested/free-text role, enter typical tasks, optionally enter tools/domain, and declare a level.
3. The user may skip placement or complete 10–15 adaptive generated questions and accept/ignore the recommendation.
4. The user can start a lesson from a scenario, supported document, or personalized random topic.
5. A document exceeding supported limits or requiring OCR is rejected with a clear message.
6. A document lesson lets the learner confirm a suggested section and grounds annotations in source spans.
7. A standard lesson contains 3–7 adapted items and 4–6 supported multiple-choice questions.
8. Incorrect answers receive immediate feedback and a varied delayed retry.
9. Completed answers deterministically update item mastery and SM-2 review dates.
10. Restarting the application preserves profile and progress but not document, lesson, or translation content.
11. Due items appear as the primary Home action, with a maximum five-item skippable review.
12. A later lesson visibly adapts to previously recorded strengths and weaknesses.
13. Translation produces natural and learning versions using explicit audience, channel, and intent/tone context.
14. Translation content is not persisted and does not increase mastery.
15. Users can reset progress or delete their profile.
16. The core end-to-end learning loop can be completed in under 10 minutes without developer assistance.

## 19. Deferred Decisions and Risks

### Deferred decisions
- Formal accessibility baseline and testing were skipped.
- Detailed model-quality evaluation methodology was skipped.
- Detailed prompt-injection policy was skipped.
- Product name remains undecided.

### Key risks
1. **Generated placement reliability:** Trusting LLM answer keys can produce inaccurate estimates. Mitigation: recommendation-only authority, unverified labeling, retake/ignore controls, and low-confidence mastery evidence.
2. **JLPT mapping ambiguity:** Official comprehensive level lists are not consistently available for all grammar and workplace expressions. Mitigation: store source/provenance and confidence; avoid strict gating.
3. **Multiple-choice guessing:** Correct guesses can overstate ability. Mitigation: small gains and repeated varied success across sessions.
4. **Document confidentiality:** Users may upload sensitive workplace text. Mitigation: ephemeral processing, visible warnings, strict size/type limits, and no source persistence.
5. **Prompt injection in documents:** Policy remains unresolved. This must be addressed before document upload is considered production-ready.
6. **Model schema compliance:** Tsuzumi 2 may produce malformed structured output. Mitigation: Pydantic validation, one repair attempt, then GPT-5 mini fallback.
7. **Local authentication limitations:** The MVP login is not enterprise identity. Mitigation: label it clearly and preserve a migration boundary.
8. **Credential exposure:** The prototype contains an embedded API key. Mitigation: immediate revocation/rotation and environment-based secrets.

## 20. Recommended Build Order

1. Secret management and configuration
2. SQLAlchemy schema and local authentication
3. Onboarding/profile workflow
4. Learning item, mastery, and simplified SM-2 services
5. Structured model client with Tsuzumi 2 retry and GPT-5 mini fallback
6. Generated scenario/random lesson workflow
7. Quiz rendering, feedback, and deterministic progress updates
8. Home review queue and Progress dashboard
9. Translation workflow
10. TXT/PDF extraction, section selection, and source-grounded annotations
11. Optional adaptive placement
12. Reset/delete controls and end-to-end demo hardening
