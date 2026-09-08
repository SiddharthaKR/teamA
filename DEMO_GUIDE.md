# Demo guide — AI Japanese Teacher

A flexible guide, not a script. Know the beats and what to expect; say it in your own words. Aim for ~5 minutes: ~45s pitch, ~3 min demo (two killer moments), ~1 min ask + Q&A.

## Before you start (checklist)
- [ ] `.env` set; for the demo keep `JLT_PRIMARY_MODEL=gpt-5-nano` (fast, no Tsuzumi-hang risk). Mention Tsuzumi in the pitch, don't depend on it live.
- [ ] `uv run pytest` is green; app started with `uv run streamlit run app.py`.
- [ ] Logged in, profile filled. Pick **N4** for the gentler "pick a line" roleplay, **N3** to show free-typed Japanese.
- [ ] `samples/demo_deck.pptx` ready in the file picker.
- [ ] A browser tab already on the app so there's no cold start on stage.
- [ ] Fallback line if a call is slow: "it's generating live against the model — while it runs, here's what's happening…" (keep talking).

## Opening (~45s) — the hook
- The pain: skilled global staff in Japan can pass JLPT but can't *operate* at work; AI-written Japanese gets **spotted as AI** (wrong keigo, literal phrasing, wrong flow).
- The idea: one app that teaches, lets you **rehearse real situations**, and makes your Japanese **read like a person wrote it**.
- Why you: built on NTT's **Tsuzumi** for the Japanese, with the structured logic fenced off so scoring is deterministic, not vibes.

## Killer moment 1 — Presentation localizer + deck-type flow (~90s)
Do:
1. Presentation page → Audience = executive, Deck type = **Technical** (or Business).
2. Upload `samples/demo_deck.pptx` → **Localize to Japanese**.

Expect (varies run to run):
- ~20s, then per-slide natural Japanese (noun-ending style, minimal katakana-English) + speaker notes + a "what changed & why" note.
- A **flow review** that reorders for the deck type — Technical puts *The Problem* first; Business leads with the recommendation.

Say (while it renders):
- On a slide: "it didn't translate literally — it chose natural business phrasing and fixed the register."
- On the flow review: "it restructured the deck the way a Japanese *technical* audience expects. Change the deck type and this advice changes." (Optional: flip to Business, re-run, show the order change.)
- Land it: **"This is the part that stops it reading as AI."**

## Killer moment 2 — Situation roleplay with a curveball (~75s)
Do:
1. Learn → lesson from a scenario ("confirm a requirement with my manager"), or the fixture lesson to get there fast.
2. Finish the quiz → **Practice this conversation** → read the brief (finish-line shown up front) → Start.
3. Respond to the opening, then the **curveball**, and submit.

Expect: a scorecard (goal / comprehensible / register / recovered) + a tip. A thin answer may **not** graduate.

Say:
- "It shows me the finish line before I start."
- If it withholds a pass: lean in — "it won't rubber-stamp me; that's the point — evidence-based, not flattery," then retry with a fuller answer to show a graduation.

## Optional (~15s) — reliability
Only if a judge probes robustness: the app **never dead-ends** — a ready-made lesson always loads and generation has two-model fallback.

## Close + the ask (~45s)
- For: enterprises onboarding foreign engineers/staff in Japan; global firms with JP offices.
- Why now: more foreign hires + labor shortage; generic AI isn't trusted for client-facing Japanese.
- Why us: workplace-situation focus + Tsuzumi + the deterministic mastery loop.
- The ask: the amount and what it funds (pilot with N companies, content depth, a metric you'll prove).

## Anticipated Q&A — talking points, not scripts
- **vs ChatGPT / DeepL:** not translation — role-aware localization + rehearsal + evidence-based mastery, tuned so output isn't spotted as AI. Show the deck-type flow reorder as proof.
- **How do you know the Japanese is good?** Deterministic scoring + structured validation; model proposes, app decides. Honest gap: no formal linguistic eval yet — part of the ask.
- **Data privacy?** Lessons, documents, translations are ephemeral; only compact progress is saved; runs locally.
- **Moat?** Workplace-situation data + the mastery model + Tsuzumi/Japan positioning.
- **Business model?** Per-seat enterprise onboarding license; expand by role packs.
- **Why Tsuzumi + GPT?** Tsuzumi for natural Japanese, a structured model for strict-JSON logic; per-phase routing + fallback.
- **AI judge:** it parses the repo — the README states problem → solution → architecture → reliability clearly.

## If something breaks
- Slow call → talk over it; don't refresh.
- Generation error → the fixture/sample lesson loads; "that's the safety net — it never dead-ends," move on.
- Quiz won't prepare → retry once; else pivot to the presentation localizer (strongest moment anyway).
- Never debug live. Narrate intent, switch to a working feature.

## Honest guardrails
- Say "demo / prototype," not "production."
- If asked for users/accuracy numbers you don't have, say so and frame it as what the funding proves. Candor beats inflated claims.
