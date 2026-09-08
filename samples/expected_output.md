# Presentation toolkit — reference output (demo_deck.pptx)

Live runs of `samples/demo_deck.pptx` (the 6-slide English pitch of this app) through the Presentation tools, kept as a "what good looks like" reference. Generated with `gpt-5-nano`; audience = executive, formality = formal. Deck type steers structure, tone, and coaching.

## Localize — deck_type = business (product demo pitch)

| # | English title | Japanese title | Japanese body (excerpt) |
|---|---|---|---|
| 1 | AI Japanese Teacher | AI日本語教師 | 職場日本語の学習／ロールプレイ／プレゼンテーション練習 |
| 2 | The Problem | 課題 | 汎用AIツールは直訳、ニュアンスを取りこぼす／出力がAIらしく見える要因：敬語の誤用・不自然な表現 |
| 3 | A Personalized Learning Loop | 個別化された学習ループ | 役割・業務・JLPTレベルに応じて適応／実証的習得を評価する小テスト／間隔反復で復習を最適化 |
| 4 | Situation Roleplay | 状況別ロールプレイ | 相手の予期せぬ一言への対応／ゴール・理解度・敬語・語調の適切さ・リカバリーを評価 |
| 5 | Presentation Toolkit | プレゼンテーション・ツールキット | 英語デッキを自然な日本語へローカライズ／聴衆に合わせた敬語の整合／読み上げポイントと話し方ガイド |
| 6 | Reliable and Ready to Demo | 信頼性とデモ対応完了 | 二モデルのフォールバックで生成継続／行き詰まらない／ローカル実行／学習サイクルを10分未満で |

## Flow review differs by deck type (same deck, same slides)

The reviewer checks the *ideal structure for the chosen type*, so the recommended running order changes:

| Deck type | Recommended order (by slide title) | Why |
|---|---|---|
| Technical | The Problem → Learning Loop → Roleplay → Toolkit → Reliable → (title) | Problem-first for an evidence-driven deck (problem → analysis → solution → result) |
| Work status | (title) → Learning Loop → Roleplay → Toolkit → Reliable → The Problem | Lead with status/progress; the Problem framing is not what a status update opens on |
| Business / proposal | **Reliable and Ready to Demo → The Problem → Learning Loop → Roleplay → Toolkit → (title)** | Lead with the recommendation and business impact (PREP / conclusion-first) |

## Delivery coaching (position-aware transitions + type flavor)
- Slide 1 (first) — opener, not 次に: `それでは、始めます。`
- Slide 6 (last) — closing, business flavor: `それでは、最後に本日の結論とインパクトをご紹介します。`

## Sample delivery judged (slide 1, business)
Delivery: `皆様、本日はお集まりいただきありがとうございます。結論から申し上げますと、本ツールは職場の日本語の習得を加速し、自信を持って発表できるよう支援します。`
Verdict: covers = yes, comprehensible = yes, register = yes → **passed**. Tip: start with the business impact in one sentence, then link to measurable outcomes.

## Notes
- Deck types available: business, technical, status (work status/progress), casual_di (casual / D&I / awareness), speech (presentation/speech).
- Run routed to `gpt-5-nano`; keep `JLT_PRIMARY_MODEL=gpt-5-nano` for the demo unless Tsuzumi is confirmed running.
- Timings: localize (6 slides + flow) ~21s; coaching (6 slides) ~17s; slides run in parallel.
