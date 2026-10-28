# Phase 3 continuation note — 2026-10-28

Branch: `v3`. Phase 3 is in progress. The broad team accuracy review belongs to Phase 5 before pilot recruitment; initial domain packs still need a named review before use.

## Built so far

- `0cba32d`: Azure OpenAI routing with local `.env` placeholders, milestone choice and short setup, personal term preview/storage, quiz concealment, separate-day progress policy `t05-v2`, and a pure word-priority function.
- `a272548`: verified, level-appropriate public personal words can become required targets in blank surprise lessons. Generated content is rejected when a selected word is absent from the dialogue or the validated quiz targets. Explicit scenarios and Explain mode do not receive these personal targets.
- Current rotation slice: at most one personal word per focused surprise lesson; least-exposed eligible words rotate, mastered words wait until due, and a checkbox lets the learner override the default. Personal focus defaults on for the first and every third completed lesson, leaving other surprise lessons open to varied topics. The fixed mock fixtures cannot generate arbitrary personal words; use a configured model for that path.
- Next slice: `situation_words_v1.json` maps four English workplace situations to words from the existing `business-v1` lexicon. Local code validates references, filters by level and mastery, rotates by exposure, and passes up to two targets in the existing generation request. The mapping is a draft pending a named human relevance review; dynamic targeting is off in mock mode because fixed fixtures cannot honor arbitrary target lists.

## Next work

1. Review and broaden the situation mapping; finish contextual domain and conversation-partner preferences, used only where relevant to the learner's scenario.
2. Build versioned general-office and role packs, with dictionary-backed IDs, provenance, fallback, and named review before use. Add due words outside the personal list to target selection.
3. Build milestone situation and language-track routes, then a user-scoped “Today” plan with due reviews and one explained next lesson.
4. Add typed recall, contextual sentence reviews, confusion feedback, remaining tracks, and the three-role Phase 3 exit walkthrough. See `docs/superpowers/plans/2026-10-27-phase-3-personal-learning.md` for acceptance checks.

## Verification and configuration

The full offline suite and architecture check passed after the rotation slice. No live Azure call has run. The ignored `.env` needs `JLT_MODEL_PROVIDER=azure`, Azure endpoint, key, and deployment names supplied locally; leave `JLT_AZURE_API_VERSION` unset for `/openai/v1`.
