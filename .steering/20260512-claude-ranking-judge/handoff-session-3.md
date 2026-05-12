# Session 3 引き継ぎ doc — Phase 5.2 / Task 5.2.5 → 5.2.7 完了

| 項目 | 値 |
|---|---|
| Session 3 期間 | 2026-05-13 |
| ステアリング ID | `20260512-claude-ranking-judge` |
| 完了範囲 | Phase 5.2 / Task 5.2.5 + Task 5.2.6 + Task 5.2.7（review 指摘修正 3 回含む） |
| 進捗 | 25 タスク中 8 タスク完了（32%） |
| push 状態 | ⚠️ **未 push** — auto-deny で main 直 push が止まった。Session 4 冒頭で user 承認の上 `git push origin main` 必要 |

---

## 1. Session 3 完了サマリ

### 1.1 完了タスク

- ✅ **Task 5.2.5**: `SYSTEM_PROMPT: Final[str]` 定数追記（3,862 chars ≈ 2,500-2,800 tokens、Prompt Caching 2,048 token 下限超過）
- ✅ **Task 5.2.6**: `build_ranking_user_message(bundle) -> str` 純粋関数 + 3 helpers（`_format_holdings` / `_format_macro` / `_format_optional`）
- ✅ **Task 5.2.7**: `rank_single_with_claude` + PRD §FR5 多段縮退 3 path + 3 helpers（`_extract_json` / `_compute_bundle_hash` / `_build_fallback_result`）

### 1.2 コミット履歴（Session 3 全 6 コミット）

| commit | 内容 |
|---|---|
| `9e42dd5` | feat(ranking): SYSTEM_PROMPT 2048 token + Prompt Caching 対応 |
| `d9adf01` | test(ranking): SYSTEM_PROMPT テストを review MEDIUM 2 件分強化 |
| `fbdac05` | feat(ranking): build_ranking_user_message + TDD |
| `f7ee8a7` | fix(ranking): _format_holdings を fail-fast 化 + テスト/型注釈強化 |
| `1117b7c` | feat(ranking): rank_single_with_claude + PRD §FR5 多段縮退 |
| `3aebd25` | refactor(ranking): rank_single_with_claude review MEDIUM/LOW 4 件 |

すべて local commit、`origin/main` 未反映（Session 4 で push）。

### 1.3 テスト推移

- 423（Session 2 終了時、Task 5.2.4 完了時点）
- → +23（Task 5.2.5 SYSTEM_PROMPT、parametrize 展開）
- → -1（Task 5.2.5 review で test_存在と非空 統合削除）
- → +19（Task 5.2.6 build_ranking_user_message、parametrize 展開）
- → +1（Task 5.2.6 review で test_fund_holdings_非数値value_は_TypeError 追加）
- → +6（Task 5.2.7 rank_single_with_claude）

`pytest tests/unit/analysis/ -q --no-cov` 最終: **237 passed**。

### 1.4 ファイルサイズ警告 ⚠️

| ファイル | 行数 | 800 行 budget |
|---|---|---|
| `src/analysis/ranking_judge.py` | **888** | ⚠️ **88 行超過** |
| `tests/unit/analysis/test_ranking_judge.py` | 959 | ⚠️ 159 行超過 |
| `tests/unit/analysis/conftest.py` | 91 | OK |

→ §3 持ち越し最優先課題（Phase 6 `_common.py` 切り出し）。

---

## 2. 重要な確定事項（Session 4 必読）

### 2.1 PRD §FR5 多段縮退 3 path 命名規約

`rank_single_with_claude` の `fallback_reason` 文字列は以下で固定:

| 失敗層 | reason 文字列 |
|---|---|
| Anthropic API 例外（401/429/503/SDK エラー、JSONDecodeError 含む） | `f"api_error: {type(exc).__name__}"` |
| Pydantic 構築失敗（範囲違反 / 禁止フィールド / lens_views キー違反） | `f"schema_error: {type(exc).__name__}"` |
| `validate_no_price_predictions` で禁止 pattern 検出 | `"forbidden_pattern_detected"`（固定） |

Task 5.2.8 cache I/O / Decision Log 記録 / UI 表示で参照される識別子。**絶対に変更しない**。

### 2.2 `_build_fallback_result` の lens_views 固定値

`{"Buffett_Munger": "(不在)", "Burry": "(不在)", "Lynch": "(不在)"}`。

→ `validate_no_price_predictions` を **スキップして return** する設計（固定文字列で禁止 pattern 含まないことが自明）。`_build_fallback_result` docstring に Note セクションで明記済み。将来この lens_views 文字列を変更する場合は forbidden pattern 含まないことを必ず確認すること。

### 2.3 caller-side 計算フィールド

Sonnet 出力 JSON に **含めない** 3 フィールド（SYSTEM_PROMPT で明示禁止 + Pydantic `extra='forbid'` で reject）:

- `confidence_adjusted` → `apply_regime_confidence(confidence, regime=bundle.regime)` で caller 側計算
- `kelly_multiplier` → `compute_kelly_multiplier(parsed["ranking_score"])` で caller 側計算
- `metadata` → `RankingMetadata(...)` で caller 側構築

### 2.4 `_compute_bundle_hash` 決定論契約

`json.dumps(payload, sort_keys=True, default=str)` + SHA256。`sub_scores` / `polymarket_macro` は `{k: str(v) for k, v in ...}` で stringify 統一（float drift によるハッシュ変動防止）。**Task 5.2.8 の cache key の正本** として再利用される。

### 2.5 Anthropic SDK usage の getattr 規約

```python
input_tokens=response.usage.input_tokens,              # SDK 保証あり、直接アクセス
output_tokens=response.usage.output_tokens,            # SDK 保証あり、直接アクセス
input_tokens_cached=getattr(response.usage, "cache_read_input_tokens", 0) or 0,  # Prompt Cache ヒット時のみ存在
```

### 2.6 ruff RUF001-003 baseline

Japanese fullwidth paren/punctuation 警告 188 件は project-wide baseline。新規追加で増加するが既存パターンと同種で許容。Phase 6 で `tool.ruff.lint.ignore` 追加候補。

### 2.7 Phase 6 持ち越し（Session 3 で追加）

- ⭐ **`src/analysis/_common.py` 切り出し（最優先・実質的に Phase 5.2 完了の前提条件化）**:
  - `_extract_json` の単一真実源化（sentiment.py との drift 防止）
  - `_get_current_git_commit` の共通化
  - **ranking_judge.py を 800 行以下に戻す目的**（現状 888 行）
- ruff `RUF001/002/003` を `tool.ruff.lint.ignore` または `per-file-ignores` で抑制
- sentiment.py の `SYSTEM_PROMPT: str` → `Final[str]` 統一（ranking_judge と整合）
- `test_ranking_judge.py` を機能別に分割（959 行）

---

## 3. 残タスク（17 タスク）

### Phase 5.2 残（2 タスク）

- [ ] **5.2.8**: `rank_with_claude_batch` + 24h キャッシュ I/O（並列実行・キャッシュキー = `sha256(bundle_hash + model_version)`、parquet schema metadata に kabu_source/kabu_fetched_at 等の CLAUDE.md §9.8.4 必須）
- [ ] **5.2.9**: Phase 5.2 並列レビュー（python-reviewer + security-reviewer + code-reviewer 3 並列）

⚠️ Task 5.2.8 着手前に Phase 6 `_common.py` 切り出しを実施推奨（ranking_judge.py 888 行のまま 5.2.8 で `rank_with_claude_batch` を追加すると 1000 行突破確実）。

### Phase 5.3 シグナル束（3 タスク、★ 3 並列最大効果）

- [ ] 5.3.0: ★ Polymarket / 13F diff / Regime アダプタを 3 サブエージェント並列実装
- [ ] 5.3.1: `signal_aggregator.py` 本体（6 skill 統合 `build_signal_bundle`）
- [ ] 5.3.2: Phase 5.3 並列レビュー

### Phase 5.4 UI 統合（5 タスク）

- [ ] 5.4.0: 4 Agent 並列（MC 関数抽出 + 詳細カード widget + session_state 調査 + settings 拡張）
- [ ] 5.4.1: `_display_screening_results()` 関数抽出（§12.3 残課題解消）
- [ ] 5.4.2: Stage 2 + Stage 3 を 02_screener に組み込み
- [ ] 5.4.3: BUY フォーム経由で Claude 判定を Decision Log に記録
- [ ] 5.4.4: Phase 5.4 並列レビュー

### Phase 5.5 E2E + handoff（7 タスク）

- [ ] 5.5.0-5.5.4: Playwright シナリオ 4 件
- [ ] 5.5.5: handoff doc 起草
- [ ] 5.5.6: 最終並列レビュー + commit + push

---

## 4. 次セッション開始用プロンプト（コピペ用）

新セッションで `/clear` してから、以下を 1 メッセージで投げる:

```
Phase 5.2 残 + Phase 6 _common.py 先行切り出しから再開してほしい。Subagent-Driven で継続。

【Session 1 + Session 2 + Session 3 完了済み】
- Phase 5.1 設計フェーズ完了（PRD + design.md）
- Task 5.2.0-5.2.4: 前提情報収集 + FORBIDDEN_PATTERNS / RankingResult Pydantic / RankingSignalBundle / Stage 3 純粋関数 3 個
- Task 5.2.5: SYSTEM_PROMPT 2048 token + Prompt Caching
- Task 5.2.6: build_ranking_user_message + 3 format helpers
- Task 5.2.7: rank_single_with_claude + PRD §FR5 多段縮退 3 path + 3 helpers

【⚠️ Session 4 冒頭で実施】
1. `git push origin main`（Session 3 の 6 コミットを反映）
   - 9e42dd5 / d9adf01 / fbdac05 / f7ee8a7 / 1117b7c / 3aebd25
2. **Phase 6 _common.py 切り出し（Task 5.2.8 前提条件化）**:
   - `src/analysis/_common.py` 新規作成
   - `_extract_json` を ranking_judge.py / sentiment.py 両方から削除して移行
   - `_get_current_git_commit` を同様に共通化
   - sentiment.py の既存テスト + ranking_judge.py の既存 237 テストすべて PASS 維持
   - 目的: ranking_judge.py を 888 行 → ~830 行に戻して Task 5.2.8 で +rank_with_claude_batch しても 1000 行未満を維持

【事前読み込み（必読）】
- .steering/20260512-claude-ranking-judge/handoff-session-3.md（本ファイル）
- .steering/20260512-claude-ranking-judge/handoff-session-2.md（Task 5.2.2-5.2.4 履歴）
- .steering/20260512-claude-ranking-judge/handoff-session-1.md（Session 1 履歴）
- .steering/20260512-claude-ranking-judge/notes-5.2.md（モデル ID / Pydantic 案 C / Prompt Caching 構文）
- .steering/20260512-claude-ranking-judge/design.md の Task 5.2.8 以降
- docs/ranking-judge-prd.md（§FR5 多段縮退 / §FR6 キャッシュ TTL）
- src/analysis/ranking_judge.py（rank_single_with_claude 実装済み）
- src/analysis/sentiment.py（_extract_json / _get_current_git_commit の原本）
- tests/unit/analysis/test_ranking_judge.py / conftest.py

【次の Task】
0. push（user 承認後）
1. Phase 6 _common.py 切り出し
2. Task 5.2.8: rank_with_claude_batch + 24h キャッシュ I/O
3. Task 5.2.9: Phase 5.2 並列レビュー

【規律】
- Subagent-Driven Development: implementer 派遣 → 完了報告 → spec-reviewer + code-quality-reviewer 並列 → 次 Task
- コンテキスト 50% 超で自動的に handoff doc 作成
- main 直 push は auto-deny されるので user 承認を待つ
- SLOP 警告は PRD §FR5 mandate 語彙で発火しやすいが説明して進める
```

---

## 5. 既知の課題 / 持ち越し

### 5.1 push 未反映 ⚠️ 最優先

Session 3 の 6 commits（9e42dd5 / d9adf01 / fbdac05 / f7ee8a7 / 1117b7c / 3aebd25）が local のみ。Session 4 冒頭で user 承認の上 `git push origin main` 必要。

### 5.2 ファイルサイズ超過

- `src/analysis/ranking_judge.py`: **888 行**（800 budget +88）
- `tests/unit/analysis/test_ranking_judge.py`: **959 行**（800 budget +159）

→ Phase 6 切り出しで `_extract_json` (~22 行) + `_get_current_git_commit` (~20 行) + import 整理で 40-50 行削減見込み。test 側は機能別ファイル分割が必要。

### 5.3 SLOP 警告（Session 3 で 4 回発火）

PRD §FR5 多段縮退の必須語彙が SLOP 警告のキーワードと衝突。Session 4 でも頻発する見込み — implementer dispatch prompt 冒頭に「PRD §FR5 mandate であり ad-hoc workaround ではない」と明記して進める運用で対処済み。

### 5.4 Phase 6 候補（Session 3 で追加されたもの一覧）

- `_common.py` 切り出し（最優先）
- ruff RUF001-003 ignore
- sentiment.py の `Final[str]` 統一
- `test_ranking_judge.py` 機能別分割
- `_extract_json` error message の sentiment/ranking 統一（Session 3 で部分対応、`"ranking judge response"` / `"sentiment analysis response"` で区別中）

### 5.5 Sonnet 価格 / モデル ID 動的取得（Session 1/2 から継続）

`anthropic.models.list()` 経由で `DEFAULT_MODEL_VERSION` を起動時取得、settings.py env var override。

### 5.6 Prompt Caching ヒット率実測ダッシュボード

Phase 5.5 E2E 実機テスト時に `metadata.input_tokens_cached / (input_tokens + input_tokens_cached)` を集計してダッシュボード化。想定 90% 削減検証。

### 5.7 §12.3 BUY 後テーブル消失問題

Phase 5.4 で session_state refactor と同時解消予定（変更なし）。

---

## 6. Subagent-Driven 運用上の学び（Session 3 で得た）

### 6.1 design.md verbatim 採用が timeout 回避に効く

Task 5.2.7 の implementer dispatch で design.md の Step 2 完全コードを spec として渡したところ、subagent が judgment call を入れる余地が減り、1 派遣で完了（247 行追加 + 6 テスト + commit）。Session 2 §6.1 「プロンプト簡潔化」の発展形として「**仕様書側で完全コードを書いて subagent には verbatim 採用を許可する**」が有効。

### 6.2 review-driven 改善のサイクルが安定

Task 5.2.5: APPROVE + MEDIUM 2 件 → 1 fix dispatch
Task 5.2.6: APPROVE + MEDIUM 2 件 + LOW 2 件 → 1 fix dispatch（4 件まとめて）
Task 5.2.7: APPROVE + MEDIUM 3 件 + LOW 2 件 → 1 fix dispatch（MEDIUM 1 件は Phase 6 持ち越し、残 4 件まとめて）

→ **review 1 回 → 修正 1 commit** のリズムが定着。implementer/reviewer/fix-implementer の 3 subagent で 1 task 完了が標準化した。

### 6.3 SLOP 警告との折り合い

`fallback` / `recovery` / `workaround` 等の語彙が SLOP 警告をトリガーするが、PRD §FR5 多段縮退は architectural mandate。dispatch prompt の冒頭で「PRD §FR5 mandate であり ad-hoc workaround ではない」と明示する規律で進めた（Task 5.2.7 dispatch）。Session 4 でも同様の対応継続。

### 6.4 Session 内 fix で自分の prompt ミスも訂正

Task 5.2.6 で `silent 0.0` 縮退を implementer prompt に書いてしまい、code-reviewer が CLAUDE.md §9.3 違反として指摘。fix dispatch で fail-fast (`TypeError`) に変更。**implementer prompt 自体も review で訂正されうる**という学び。

### 6.5 ファイルサイズが Task 完了の制約になる

Task 5.2.7 終了時点で ranking_judge.py が 888 行に到達し、Task 5.2.8 の追加でほぼ確実に 1000 行超過。**機能 task 完了の途中で refactor task（Phase 6 _common.py）を挟む判断**が必要になった。今後の Phase 5.3 以降でも同様の判断局面が発生する見込み。

---

**Session 3 終わり** — Session 4 では push → Phase 6 _common.py 切り出し → Task 5.2.8 → Task 5.2.9 の順で再開。
