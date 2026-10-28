# Phase 3 word-set relevance review

Status: pending a named human reviewer. These are draft memberships; every expression is resolved against `business-v1` by offline tests. The files retain their versions so a reviewer can inspect the exact proposal before it changes.

## Domain packs (`domain_packs_v1.json`)

| Pack | Intended learner context | Proposed expressions |
| --- | --- | --- |
| General office | Unmatched role/domain fallback | 会議, 報告, 確認, 予定, 連絡, 相談, 資料, 依頼 |
| Software | Software/developer role or software/programming domain | 仕様, 要件, 設計, 開発, 実装, 試験, 不具合, 修正 |
| Project management | Project/program manager role or planning domain | 進捗, 調整, 期限, 担当, 課題, 提案, 確認, 共有 |
| Sales | Sales/account executive role or customer domain | 顧客, 取引先, 見積もり, 契約, 提案, 問い合わせ, 対応, 納期 |

## Situation sets (`situation_words_v2.json`)

| Situation | Proposed expressions |
| --- | --- |
| Status update | 報告, 進捗, 確認, 予定 |
| Meeting | 会議, 議題, 資料, 確認 |
| Scheduling | 予定, 日程, 締め切り, 納期 |
| Requirements | 仕様, 確認, 課題 |
| Handover | 共有, 担当, 資料, 確認 |
| Customer follow-up | 顧客, 連絡, 対応, 確認 |

## Review record

The route catalog also proposes word pairs (連絡/相談, 会議/意見, 説明/提案), grammar forms (〜てください, 〜ましょうか, 〜なければなりません), and ordered workplace phrases (お疲れ様です, よろしくお願いいたします, お世話になっております). Please check that each suits its milestone and that each phrase has one reasonable chunk order before treating the local check as pedagogically reviewed.

- Reviewer name: pending
- Review date: pending
- Verdict for each pack and situation: pending
- Corrections or exclusions: pending

Check that every set fits its named situation or role, that its words make sense at the learner's level, and that the handover/customer triggers do not pull in unrelated social scenarios. The test suite verifies reference resolution and basic level filtering; it cannot judge pedagogical relevance.
