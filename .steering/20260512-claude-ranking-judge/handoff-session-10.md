# Session 10 引き継ぎ doc — Phase 6.3 派生 reviewer fix セット + Protocol 型付け完了 ✅

| 項目 | 値 |
|---|---|
| Session 10 期間 | 2026-05-16 |
| ステアリング ID | `20260512-claude-ranking-judge` |
| 完了範囲 | Phase 6.3 派生 reviewer fix セット (4 件) + anthropic_client Protocol 型付け (handoff §4.13 解消) + 各 commit に対する 2 reviewer 並列レビュー fix |
| 進捗 | Phase 6 全 13 タスク候補 (handoff-session-8 §7) のうち Session 10 で **4 タスク完了** (累計 9/13)。残 4 候補 + Phase 6.3 派生 8 件持ち越しを Phase 6.4 以降へ |
| push 状態 | ✅ 4 commit (`1d75ef0` → `ec789cd` → `6559e86` → `0f45545`) を origin/main に push 済 (`10064c5..0f45545`) |
| 累積 commit | `10064c5` (Session 9 handoff) → `1d75ef0` (派生本体 4 件) → `ec789cd` (派生 reviewer fix 4 件) → `6559e86` (Protocol 型付け本体) → `0f45545` (Protocol reviewer fix 3 件) |

---

## 1. Session 10 完了サマリ

### 1.1 Phase 6.3 派生 reviewer fix セット (handoff-session-9 §7 #3 + #4 + #5)

handoff-session-9.md §7 で「Phase 6.2 派生 reviewer fix 3 件セット (Recommended)」として提示されたタスクを完全消化。

#### 1.1.1 #3 compute_mu_for_monte_carlo を analysis 層へ移管 (handoff §4.1 派生、reviewer HIGH-2 解消)

`src/dashboard/views/_screener_compute.py` (dashboard 層) → `src/analysis/ranking_judge.py` (analysis 層) の Stage 3 純粋関数群へ移動。`RankingSignalBundle` owner と同居させ、dashboard 層 → analysis 層への依存方向を正しく保つ。

テスト rename: `tests/unit/dashboard/views/test_screener_compute_mu.py` → `tests/unit/analysis/test_ranking_judge_monte_carlo.py` (git 69% similarity 検出)。

#### 1.1.2 #4 FALLBACK_REASON_LABELS を ranking_judge.py に集約 (handoff §2.3 / §4.2 派生)

`widgets/ranking_card.py` から `analysis/ranking_judge.py` へ移管。`FallbackReason` Literal の真理値と同居させることで、両 consumer (`_screener_compute` / `ranking_card`) が単一情報源を共有 (handoff §2.3「両 consumer の単一情報源」規律)。

`TestFallbackReasonLabelsCoverage` 2 件追加: `typing.get_args(FallbackReason)` と `FALLBACK_REASON_LABELS.keys()` の集合一致を構造的検証 (reviewer LOW-1 解消)。

#### 1.1.3 #5 _screener_compute.py:879 外側 catch の type(exc).__name__ 露出修正 (handoff §4.3 派生)

`st.error(f"🚨 Claude 判定全体失敗: {type(exc).__name__}...")` を `classify_api_exception` + `FALLBACK_REASON_LABELS` 経由の日本語ラベル表示に置換。`isinstance(exc, anthropic.APIStatusError)` 分岐 + lazy `import anthropic` を撤去。401 → "auth_error" でラベル意味維持、status_code は logger に残す。

### 1.2 Phase 6.3 派生 reviewer 並列レビュー fix (commit `ec789cd`)

`1d75ef0` (派生 4 件本体) に対し `python-reviewer` + `code-reviewer` を並列起動。指摘 8 件のうち **2 視点一致 3 件 + 軽微 1 件 = 4 件 fix**、4 件は Phase 6.4 持ち越し。

| 視点一致 | 指摘 | fix 内容 |
|---|---|---|
| ✅ 2 視点 MEDIUM | `_FALLBACK_REASON_LABELS` / `_classify_api_exception` の private cross-module import → public 化推奨 | leading underscore 削除、6 ファイル一斉更新 |
| ✅ 2 視点 (HIGH+MEDIUM) | `compute_mu_for_monte_carlo` の引数粒度 (bundle 全体 → momentum_12m スカラー) | シグネチャ変更、`_BundleStub` + `type: ignore[arg-type]` 5 件削除 (code-r LOW-1 と同時解消) |
| 単独軽微 | python-r MEDIUM-2: `FALLBACK_REASON_LABELS` コメント事実誤認 (「mypy/pyright が key 未登録を検出」 → pytest TestFallbackReasonLabelsCoverage で網羅性保証) | コメント訂正 |

### 1.3 anthropic_client Protocol 型付け (handoff-session-9 §7 #10、commit `6559e86`)

handoff §4.13 で「Phase 6.2 で `import anthropic` を module top に移動した foundation の上に **Phase 6.3 で着手しやすくなった**」と明記されていたタスクを消化。

#### 1.3.1 新規 `src/analysis/anthropic_types.py` (107 行) — Protocol 定義 3 種

```python
class AnthropicMessagesResource(Protocol):
    def create(self, **kwargs: Any) -> Any: ...

class AnthropicModelsResource(Protocol):
    def list(self, **kwargs: Any) -> Any: ...

class AnthropicLike(Protocol):
    @property
    def messages(self) -> AnthropicMessagesResource: ...
    @property
    def models(self) -> AnthropicModelsResource: ...
```

PEP 544 structural typing で `unittest.mock.MagicMock` も duck-typing で satisfy する設計。`@runtime_checkable` は付与しない (静的検査のみで十分)。

#### 1.3.2 型注釈変更 5 ファイル

| ファイル | 関数 | 変更 |
|---|---|---|
| `ranking_judge.py` | `rank_single_with_claude` | `Any` → `AnthropicLike` (内部 None ハンドリングなし、非 None 必須) |
| `ranking_judge_cache.py` | `rank_with_claude_batch` | `Any` → `AnthropicLike` |
| `sentiment.py` | `analyze_sentiment` | `Any` → `AnthropicLike` |
| `_sonnet_model_resolver.py` | `resolve_sonnet_model_version` | `Any` → `AnthropicLike \| None` (内部 None 分岐あり) |
| `_screener_compute.py` | `analyze_recommendation_for_ticker` | `Any` → `AnthropicLike` (caller L568 で narrowing 済) |
| `_screener_compute.py` | `run_screening_pipeline` | `Any` → `AnthropicLike \| None` (top-level) |
| `_screener_compute.py` | `_run_sonnet_stage` | `Any` → `AnthropicLike \| None` (pass-through) |

### 1.4 Protocol 型付け reviewer 並列レビュー fix (commit `0f45545`)

`6559e86` に対し 2 reviewer 並列。**2 視点一致 0 件**、単独指摘のみ。Session 9 規律 (HIGH 単独で片方 OK 評価ありは持ち越し) に従い **3 件 fix**、4 件持ち越し。

| 指摘 | 視点 | fix |
|---|---|---|
| code-r HIGH-1 | `_anthropic_types.py` の leading underscore (Phase 6.2 で public 化したパターンと非対称) | rename `_anthropic_types` → `anthropic_types` (git mv で history 保持) |
| python-r MEDIUM-2 | `_run_sonnet_stage` の暗黙 narrowing (mypy/pyright で flag 可能) | 明示的 `anthropic_client is None` ガードを既存条件に統合 |
| (バグ修正) | prior commit `6559e86` で `ranking_judge_cache.py` / `sentiment.py` の `AnthropicLike` import 抜け | 2 ファイルに import 追加 |

**prior commit のバグについて**: `from __future__ import annotations` で型注釈が文字列化されるため runtime / pytest は影響を受けず 572 tests も passed だったが、型チェッカ観点では `AnthropicLike` が未定義の forward reference (dead annotation)。本 commit で完全化。

### 1.5 commit 履歴 (Session 10 全 4 commit)

| commit | 内容 | 行数差 |
|---|---|---|
| `1d75ef0` | refactor(phase-6.3): 派生 reviewer fix 4 件 — FALLBACK_REASON_LABELS 集約 + compute_mu 移管 + 外側 catch 抽象化 + 網羅性 pytest | +140/-67 |
| `ec789cd` | refactor(phase-6.3): 2 reviewer 並列レビュー指摘 fix (2 視点一致 3 件 + 軽微 1 件) | +75/-91 |
| `6559e86` | refactor(phase-6.3): anthropic_client Protocol 型付け (handoff §4.13 解消) | +119/-8 |
| `0f45545` | refactor(phase-6.3): Protocol 型付け reviewer fix — public rename + None ガード + 抜け import 補完 | +18/-6 |

合計: **+352 / -172 行**、累計 16 ファイル変更 + 2 新規ファイル (`anthropic_types.py` 107 行 + `test_ranking_judge_monte_carlo.py` ≈70 行 [旧 mu test rename])。

---

## 2. 重要な確定事項（Session 11 必読）

### 2.1 FALLBACK_REASON_LABELS / classify_api_exception の public 化規律 (Phase 6.3 確定)

Phase 6.2 で導入された `_FALLBACK_REASON_LABELS` / `_classify_api_exception` は **Phase 6.3 で leading underscore を削除した public シンボル**に格上げ。cross-module import される実態と Python 慣習を整合させた。

新しい `FallbackReason` Literal 値追加時の手順:
1. `_classify_api_exception` の isinstance ブランチを追加
2. `FallbackReason` Literal に新しい値を追加
3. `FALLBACK_REASON_LABELS` に日本語 mapping 追加
4. `TestFallbackReasonLabelsCoverage` が自動検出 (網羅性 pytest)

### 2.2 AnthropicLike Protocol の運用規律 (Phase 6.3 確定)

`anthropic_client: Any` は `anthropic_client: AnthropicLike` または `AnthropicLike | None` に置換完了。新規関数を追加する際は:

- **API を内部で呼ぶ関数** (`.messages.create()` / `.models.list()`): `AnthropicLike`
- **None も受け入れて gate する関数**: `AnthropicLike | None` + 明示的 `if x is None: ...` narrowing
- テスト時の `unittest.mock.MagicMock` は duck-typing で satisfy するため既存テスト無修正で通る

### 2.3 compute_mu_for_monte_carlo の引数粒度パターン (Phase 6.3 確定)

Stage 3 純粋関数群 (`apply_regime_confidence` / `compute_kelly_multiplier` / `compute_mu_for_monte_carlo`) は **スカラー引数を受ける**形式で統一。`RankingSignalBundle` 全体を渡さず、必要なフィールドだけを呼び出し側で取り出す。

呼び出し例: `compute_mu_for_monte_carlo(bundle.momentum_12m)` (`_screener_display.py:478`)。

### 2.4 _anthropic_types vs anthropic_types 命名規約 (Phase 6.3 確定)

`leading underscore` モジュール命名は **モジュール内部実装の隠蔽**に限定する。複数モジュールから cross-module import される Protocol 定義モジュールは `_` なしで public とする (`anthropic_types.py`)。Phase 6.2 の `_FALLBACK_REASON_LABELS` → `FALLBACK_REASON_LABELS` 公開と同方向。

### 2.5 `from __future__ import annotations` 下のバグ検知盲点 (Session 10 新規)

`from __future__ import annotations` で型注釈が文字列化される環境では、**未定義の型名を参照しても runtime / pytest は通過してしまう** (`AnthropicLike` import 抜けが pytest 572 passed のままだった)。Phase 6.4 以降で追加すべき防御:

- 型チェッカ (mypy / pyright) を CI に組み込み、forward reference 解決失敗を検出
- `typing.get_type_hints()` を使う場合は `include_extras=True` で明示的 resolve

### 2.6 main 直 push の auto-deny 規律継続 (Session 6/7/8/9/10 共通)

Session 10 でも main 直 push は auto mode classifier で deny される。Phase 6.3 の 4 commit は user の手動 `! git push origin main` で push 完了。

### 2.7 reviewer 2 視点一致 0 件のケース判定 (Session 10 新規)

Protocol 型付け commit (`6559e86`) の reviewer 並列では **2 視点一致が 0 件** (全て単独指摘) というケースが発生。Session 9 規律「HIGH 単独でも fix する (片方が明確に問題なし評価していない限り)」を適用:

- code-r HIGH-1 (rename): python-r 言及なし = 暗黙的に「問題なし」評価ではない → **fix する**
- python-r MEDIUM-1 (`@property` vs attribute): code-r が「Protocol 仕様上問題なし」と**明示評価** → **持ち越し**
- python-r MEDIUM-2 (narrowing): 単独だが mypy strict での実害可能性 → **fix する**

判定基準: 「明示評価」と「言及なし」は別物。後者は規律上 fix 推奨。

---

## 3. 残タスク

Phase 6 全 13 タスク候補 (handoff-session-8 §7) のうち **Session 10 で 4 件消化** (累計 9 件)。残 4 候補 + Phase 6.3 派生 8 件 = 12 件を Phase 6.4 以降へ持ち越し。

---

## 4. 既知の課題 / 持ち越し (Phase 6.4 以降)

handoff-session-9 §4 から Phase 6.3 で解消したもの:

- ✅ §4.1 派生 (compute_mu を analysis 層へ) → Phase 6.3 で解消
- ✅ §4.2 派生 (FALLBACK_REASON_LABELS 網羅性) → Phase 6.3 で TestFallbackReasonLabelsCoverage 解消
- ✅ §4.3 派生 (外側 catch type(exc).__name__ 露出) → Phase 6.3 で classify_api_exception 経由解消
- ✅ §4.13 (anthropic_client Protocol 型付け) → Phase 6.3 で AnthropicLike 解消

**未解消 + Phase 6.3 派生 + Phase 6.3 Protocol 派生**:

### 4.1 ranking_judge.py 1016 行 → 4 ファイル分割 (handoff-session-9 §4.5、Session 10 で +58 行)

**優先度: 最高** (handoff-session-9 §7 #1、Session 10 で更に肥大化)。

推奨分割案 (依存方向昇順):

1. **`ranking_judge_schema.py`** (~300 行): `RankingMetadata`, `RankingResult` (Pydantic), `RankingSignalBundle`, `FORBIDDEN_PREDICTION_FIELDS`, `FORBIDDEN_PATTERNS`, `contains_forbidden_pattern`
2. **`ranking_judge_prompt.py`** (~150 行): `SYSTEM_PROMPT`, `build_ranking_user_message`, `_format_holdings`, `_format_macro`, `_format_optional`, `_compute_bundle_hash`
3. **`ranking_judge_recovery.py`** (~200 行): `FallbackReason`, `FALLBACK_REASON_LABELS`, `classify_api_exception`, `_build_fallback_result`, Stage 3 純粋関数 (`apply_regime_confidence`, `compute_kelly_multiplier`, `compute_mu_for_monte_carlo`, `validate_no_price_predictions`)
4. **`ranking_judge.py`** (~250 行): `rank_single_with_claude` (orchestrator) + `DEFAULT_MODEL`/`_VERSION`/`_MAX_TOKENS`/`ACADEMIC_SOURCE` 定数 + 末尾 re-export 集約

実装手順 (1 ファイル毎承認ゲート、CLAUDE.md §7):
- Phase 6.4.A: schema 抽出 (依存なし、最先発で安全)
- Phase 6.4.B: prompt 抽出 (schema を import)
- Phase 6.4.C: recovery 抽出 (schema を import)
- Phase 6.4.D: ranking_judge.py スリム化 + re-export 整備

各段階で reviewer 並列 + 572 tests 維持。`ranking_judge_cache.py` は schema + ranking_judge を import 済み、内部の `from .ranking_judge import ...` を相対 import で維持する分には変更不要だが、re-export パターン整理時に追従が必要かもしれない。

### 4.2 _screener_compute.py 917 行 → _screener_sonnet_stage.py 分割 (handoff-session-9 §4.4)

Session 9 922 行 → Session 10 で **917 行** (-5、compute_mu 削除分 -19 + Protocol ガード追加 +14)。依然 800 行 budget 超過。`_run_sonnet_stage` 関数 (~150 行) を切り出すと ~770 行に縮む。

### 4.3 CompositeScoreInputs フィールド名 `_jpy` → `_local` リネーム (handoff-session-9 §4.6)

未着手。影響範囲大 (全サブクラス + 呼び出し側 + テスト fixture)。

### 4.4 yfinance df.attrs Provenance 未実装 (handoff-session-9 §4.7)

未着手。CLAUDE.md §9.8.1 / §9.8.6。

### 4.5 mypy Protocol 型不一致 (handoff-session-9 §4.8) + CI 統合 (Session 10 派生)

未着手。Phase 6.3 で `AnthropicLike` Protocol を導入したが、mypy 全体実行は未実施。本 Session 10 で `from __future__ import annotations` 下の import 抜けバグを発見した教訓も合わせ、**型チェッカの CI 統合を Phase 6.4 で優先**。

### 4.6 Sonnet ranking cache LRU purge (Issue #2、handoff-session-9 §4.9)

未着手。

### 4.7 Prompt Caching ヒット率実測ダッシュボード (Issue #3、handoff-session-9 §4.10)

未着手。

### 4.8 TRACKED_FUNDS CIK 実機検証 (Issue #1、handoff-session-9 §4.11)

未着手。

### 4.9 vault_path 個人パス (handoff-session-9 §4.12)

未着手。

### 4.10 ruff RUF001-003 + E501 baseline (handoff-session-9 §4.14)

449+ 件 baseline、Phase 6 で一括対応予定。

### 4.11 Phase 5.5.2 残シナリオ (b)(c)(d) (handoff-session-9 §4.15)

未着手。Playwright MCP 整備済 (Session 6)。

### 4.12 Phase 6.1 reviewer MEDIUM 持ち越し (handoff-session-9 §4.16)

未着手。

### 4.13 Phase 6.3 派生 reviewer 持ち越し (新規、Session 10 派生)

- **code-r 単独 MEDIUM-1**: `compute_mu_for_monte_carlo` を `monte_carlo.py` に再配置 (code-r 自身「現状維持で許容」明示、循環 import 懸念)
- **code-r 単独 LOW-2**: `ranking_card.py:137 .get` フォールバックパス未カバー (TestFallbackReasonLabelsCoverage で実質保証、低リスク)
- **python-r 単独 LOW**: `getattr(exc, "status_code", None)` の許容性 (「許容範囲」明示)
- **python-r 単独 LOW**: N802 kanji baseline (handoff §4.10 で一括対応予定)

### 4.14 Phase 6.3 Protocol 派生 reviewer 持ち越し (新規、Session 10 派生)

- **python-r 単独 MEDIUM-1**: `@property` Protocol vs attribute Protocol 表記の選択 (code-r が「Protocol 仕様上問題なし」明示評価、現状維持)
- **code-r 単独 MEDIUM-1**: `get_anthropic_client()` の戻り値型 `anthropic.Anthropic | None` を `AnthropicLike | None` に統一すべきか (caller 境界の意図的 concrete 型として現状維持)
- **code-r 単独 LOW-1**: `OptionalAnthropicClient = AnthropicLike | None` Type Alias 導入 (3 箇所重複は許容範囲)
- **python-r 単独 LOW**: 返り値 `Any` 許容の将来コスト (許容明示)

---

## 5. Subagent-Driven 運用の学び（Session 10）

### 5.1 commit リズム継続 (Session 5/6/7/8/9 から)

Phase 6.3 で:
- 派生本体 4 件 → **1 commit** (`1d75ef0`)
- 派生 reviewer fix 4 件 → **1 commit** (`ec789cd`)
- Protocol 本体 → **1 commit** (`6559e86`)
- Protocol reviewer fix 3 件 → **1 commit** (`0f45545`)

Session 9 (2 commit) より多いが、Phase 6.3 が 2 つの独立サブフェーズ (派生 fix + Protocol 型付け) を含むため。サブフェーズ毎に「本体 + reviewer fix」の 2 commit リズムを維持。**Phase 全体で 4 commit に集約**することで bisect / revert が容易。

### 5.2 reviewer 2 視点一致 0 件のケース判定 (Session 10 新規)

§2.7 に明文化。「言及なし」と「明示評価あり」を区別する規律を確立。code-r HIGH-1 (rename) は python-r が言及していなかったが、code-r 自身が「アーキテクチャ負債のみ」と明示しており、Session 9 規律「HIGH 単独でも fix」を適用した。一方 python-r MEDIUM-1 (`@property`) は code-r が「Protocol 仕様上問題なし」と明示評価しており、持ち越しとした。

### 5.3 prior commit 中のバグを reviewer サイクルで発見 (Session 10 新規)

Protocol 型付け commit (`6559e86`) で `ranking_judge_cache.py` / `sentiment.py` の `AnthropicLike` import が抜けていた。`from __future__ import annotations` で型注釈が文字列化されるため pytest は通過していたが、Session 10 の reviewer fix サイクルで grep ベース確認時に発見。

教訓: pytest 通過 ≠ 完全。**型チェッカ統合 (mypy/pyright CI 化) を Phase 6.4 で優先**。§4.5 / §2.5。

### 5.4 GateGuard 発火頻度の評価 (Session 10 継続)

Session 10 でも Bash / Edit / Write 各回で GateGuard が発火 (特に新規ファイル作成 + 重要ファイル編集時)。事実 4 点 (呼び出し元 / 既存ファイル不在 / データ I/O / ユーザー指示 verbatim) を機械的に提示して retry する規律が完全に定着。

Session 中盤以降は同セッション内で発火頻度が減るが、リネーム + import 補完で多数の Edit が発生したため頻度は高め。

### 5.5 SLOP 警告との付き合い方 (Session 7/8/9 から継続)

Session 10 でも:
- `fallback` 語句に対する SLOP 警告: handoff §4.6 で明示的に正当化された PRD §FR5 多段縮退規律の延長 (`classify_api_exception` + `FALLBACK_REASON_LABELS` の三位一体パターン) であり ad-hoc 縮退 layer ではないため説明して進める
- Read 警告 (`Extensive reading`): 18 ファイル超で警告。Phase 6 後半に向けて Grep / `git show` でピンポイント参照に置換する方向

---

## 6. メトリクス・サマリ

### 6.1 Phase 6.3 全体メトリクス

| 指標 | 値 |
|---|---|
| 完了タスク | 4 / 4 (100%) — handoff-session-9 §7 から #3 + #4 + #5 + #10 |
| Session 数 | 1 (Session 10 で完走) |
| commit 数 | 4 (派生本体 + 派生 reviewer fix + Protocol 本体 + Protocol reviewer fix) |
| 並列実装 Agent 数 | 0 (自分で順次実装) |
| 並列レビュー Agent 数 | 4 (2 サブフェーズ × python + code) |
| 新規テスト | 2 件 (`TestFallbackReasonLabelsCoverage`) |
| テスト移動 | 5 件 (`test_screener_compute_mu.py` → `test_ranking_judge_monte_carlo.py`) |
| 全レイヤー pytest | **572 passed** (EODHD 実 API 除外) — Session 9 から +2 |
| reviewer 指摘 fix | 7 件 (派生 4 + Protocol 3) |
| Phase 6.4 持ち越し reviewer 指摘 | 8 件 (派生 4 + Protocol 4) |
| CRITICAL/BLOCK | 0 / 0 |

### 6.2 Phase 全体進捗

| Phase | 完了 | 残 |
|---|---|---|
| 5.1〜5.5 | ✅ 25/25 (100%) | - |
| 6.1 Decimal §9.1 fix | ✅ 5/5 (100%) | - |
| 6.2 §9.1 残 + 軽量整理 | ✅ 4/4 (100%) | - |
| **6.3 派生 reviewer fix + Protocol 型付け** | **✅ 4/4 (100%)** | - |
| 6.4 以降 | 0 | 12 候補 (handoff §4) |

### 6.3 ファイルサイズ警告サマリ (Session 9 → Session 10)

| ファイル | Session 9 終了時 | Session 10 終了時 |
|---|---|---|
| `02_screener.py` | 593 ✅ | **593 ✅** (変更なし) |
| `ranking_judge.py` | 958 ⚠️⚠️ | **1016 ⚠️⚠️⚠️** (+58、`compute_mu_for_monte_carlo` 移管 + `FALLBACK_REASON_LABELS` 集約 + Protocol import + classify_api_exception public 化、**Phase 6.4 で 4 分割優先度最高**) |
| `_screener_compute.py` | 922 ⚠️⚠️ | **917 ⚠️⚠️** (-5、`compute_mu_for_monte_carlo` 削除 -19 + lazy import anthropic 撤去 + Protocol ガード追加 +14、依然 budget 超過) |
| `_screener_display.py` | 581 ✅ | **586 ✅** (+5、`compute_mu_for_monte_carlo` 移管コメント + 引数粒度更新) |
| `_screener_session.py` | 105 ✅ | **105 ✅** (変更なし) |
| `widgets/ranking_card.py` | 225 ✅ | **214 ✅** (-11、`FALLBACK_REASON_LABELS` 移管によるコメント簡略化) |
| `anthropic_types.py` (新規) | - | **107 ✅** (新規 Protocol 定義) |

**注目**: `ranking_judge.py` 1016 行は **Phase 6.4 で 4 分割を最優先タスクとする** (§4.1)。

### 6.4 Session 10 累計

| 指標 | 値 |
|---|---|
| Session 期間 | 約 4 時間 (2026-05-16 18:11 〜 22:30 頃) |
| 並列実装 Agent 数 | 0 |
| 並列レビュー Agent 数 | 4 (2 サブフェーズ × 2 視点) |
| 反映 commit 数 | 4 (`1d75ef0` + `ec789cd` + `6559e86` + `0f45545`) |
| 反映行数 | +352 / -172 |
| handoff doc 起草 | 本ファイル (handoff-session-10.md) |
| ファイルサイズ警告 | ⚠️⚠️⚠️ `ranking_judge.py` 1016 行 (4 分割優先度最高、§4.1) / ⚠️⚠️ `_screener_compute.py` 917 行 (§4.2) |

---

## 7. 次セッション開始用プロンプト（コピペ用）

新セッションで `/clear` してから、以下を 1 メッセージで投げる:

```
Phase 6.3 完全クローズ後の Phase 6.4 から開始。Subagent-Driven で継続。

【Session 1〜10 完了済み】
- Phase 5.1〜5.5 完全クローズ ✅ (25/25 タスク)
- Phase 6.1 完全クローズ ✅ (Decimal §9.1 fix)
- Phase 6.2 完全クローズ ✅ (§9.1 残 + 軽量整理 4 件)
- Phase 6.3 完全クローズ ✅
  - 派生 reviewer fix 4 件:
    - compute_mu_for_monte_carlo を analysis 層へ移管 (reviewer HIGH-2)
    - FALLBACK_REASON_LABELS を ranking_judge.py に集約 + 網羅性 pytest
    - _screener_compute.py:879 外側 catch を classify_api_exception 経由に
    - 派生 reviewer 並列レビュー (HIGH 1 + MEDIUM 4 + LOW 4) のうち
      2 視点一致 3 + 軽微 1 を fix、4 件 Phase 6.4 持ち越し
  - anthropic_client Protocol 型付け (handoff §4.13 解消):
    - AnthropicLike Protocol 新設 (PEP 544 structural typing)
    - 5 ファイルの anthropic_client: Any → AnthropicLike (| None)
    - Protocol reviewer 並列レビュー (HIGH 1 + MEDIUM 3 + LOW 4) のうち
      3 件 fix (public rename + None ガード + 抜け import 補完)、4 件持ち越し
  - テスト 572 passed (no regression、4 commit 通して維持)

【Session 11 冒頭で実施】
**Phase 6.4 最優先タスク: ranking_judge.py 1016 行 → 4 ファイル分割** (handoff §4.1)

推奨分割案 (依存方向昇順、段階的に Phase 6.4.A → 6.4.D の 4 サブフェーズ):

Phase 6.4.A: ranking_judge_schema.py (~300 行) 抽出
  - RankingMetadata (dataclass)
  - RankingResult (Pydantic BaseModel)
  - RankingSignalBundle (dataclass)
  - FORBIDDEN_PREDICTION_FIELDS / FORBIDDEN_PATTERNS
  - contains_forbidden_pattern
  - validate_no_price_predictions
  依存: 外部のみ (pydantic, decimal, re など)、循環なし

Phase 6.4.B: ranking_judge_prompt.py (~150 行) 抽出
  - SYSTEM_PROMPT (constant)
  - build_ranking_user_message
  - _format_holdings / _format_macro / _format_optional
  - _compute_bundle_hash
  依存: schema (RankingSignalBundle)

Phase 6.4.C: ranking_judge_recovery.py (~200 行) 抽出
  - FallbackReason (Literal)
  - FALLBACK_REASON_LABELS (public dict)
  - classify_api_exception (public fn)
  - _build_fallback_result
  - apply_regime_confidence / compute_kelly_multiplier / compute_mu_for_monte_carlo
  依存: schema (RankingResult, RankingSignalBundle)

Phase 6.4.D: ranking_judge.py (~250 行) スリム化
  - rank_single_with_claude (orchestrator)
  - DEFAULT_MODEL / DEFAULT_MODEL_VERSION / DEFAULT_MAX_TOKENS / ACADEMIC_SOURCE
  - 末尾に schema / prompt / recovery / cache の re-export 集約 (既存 import 互換性維持)
  依存: schema, prompt, recovery, anthropic_types

各サブフェーズで:
- 1 commit 本体 + 必要なら 1 commit reviewer fix
- pytest 572 passed 維持
- 1 ファイル毎承認ゲート (CLAUDE.md §7)

ranking_judge_cache.py は schema + ranking_judge を既に import 済 (相対 import)、
本分割では分割先に追随して `from .ranking_judge_schema import` 等に修正。
テスト test_ranking_judge.py (135 件) は ranking_judge からの import を保ち、
re-export パターンで互換性維持 (cache 分割時の precedent あり、Phase 5.5.0)。

【事前読み込み（必読）】
- .steering/20260512-claude-ranking-judge/handoff-session-10.md (本ファイル)
- .steering/20260512-claude-ranking-judge/handoff-session-9.md (Phase 6.2 まで)
- .steering/20260512-claude-ranking-judge/handoff-session-8.md (Phase 6.1 まで)
- .steering/20260512-claude-ranking-judge/issues-carryover.md (持ち越し Issue 3 件)
- docs/ranking-judge-prd.md (§FR2 / §FR5 / §FR8 UI 表示規約)
- src/analysis/ranking_judge.py (1016 行、Phase 6.4.A-D で 4 分割)
- src/analysis/ranking_judge_cache.py (193 行、分割後 import path 修正候補)
- src/analysis/anthropic_types.py (107 行、Phase 6.3 で新設)
- src/dashboard/views/_screener_compute.py (917 行、Phase 6.4 で _screener_sonnet_stage.py 分割候補)
- src/dashboard/views/_screener_display.py (586 行)
- src/dashboard/widgets/ranking_card.py (214 行、FALLBACK_REASON_LABELS 公開後コメント簡略)
- tests/unit/analysis/test_ranking_judge.py (135 件、re-export pattern で互換性維持要)
- tests/unit/analysis/test_ranking_judge_monte_carlo.py (5 件、Phase 6.3 で移動 + 簡略化)

【代替候補 (Phase 6.4 着手時に user 確認推奨)】
1. ranking_judge.py 4 分割 (本プロンプト主推奨、§4.1)
2. _screener_compute.py 917 行 → _screener_sonnet_stage.py 分割 (§4.2)
3. CompositeScoreInputs `_jpy` → `_local` リネーム (§4.3、影響範囲大)
4. yfinance df.attrs Provenance 実装 (§4.4)
5. mypy CI 統合 (§4.5、Phase 6.3 のバグ検知盲点解消)
6. Issue 起票 (§4.6-4.8、3 件まとめて gh CLI で)
7. Phase 5.5.2 残シナリオ (b)(c)(d) を pytest-playwright で自動化 (§4.11)
8. ANTHROPIC_API_KEY 必要な実機検証

【次の Task 候補 (Phase 6.4.A 着手前)】
1. Phase 6.4 計画策定 (本 handoff §4.1 の段階分割を user に提示、優先順序確認)
2. Phase 6.4.A: schema 抽出 (依存なし、最先発で安全)
3. test_ranking_judge.py の re-export 互換性確認 (Phase 5.5.0 cache split precedent 参照)

【規律】
- Subagent-Driven Development: 4 サブフェーズ各々で implementer 派遣 → 完了報告
  → spec-reviewer + code-quality-reviewer 並列 → 次サブフェーズ
- 1 ファイル毎承認ゲート (CLAUDE.md §7) — 4 サブフェーズ × 1 ファイル = 計 4 回承認
- main 直 push は auto-deny されるので user 承認 (! git push origin main) を待つ
- Fact-Forcing Gate (GateGuard) は Bash / 新規ファイル作成 / 主要ファイル編集時に発火
- SLOP 警告は PRD §FR5 mandate 語彙で発火しやすいが説明して進める
- Playwright MCP セットアップ完了済 (Session 6) — ToolSearch で schema ロード後、実機検証可能
- reviewer の HIGH 指摘でも検証なしに信用しない (Session 8/9/10 教訓)
- HIGH 単独指摘は『片方が明確に問題なし評価なし』fix、MEDIUM は 2 視点一致で fix
- reviewer 2 視点一致 0 件のケース: 「言及なし」と「明示評価」を区別、明示評価ありなら持ち越し
- prior commit のバグは reviewer サイクル + grep 確認で発見可能 (Session 10 §5.3 教訓)
- `from __future__ import annotations` 下で型エラーが runtime/pytest を通過する盲点に注意
```

---

**Session 10 終わり** — Phase 6.3 完全クローズ ✅ (4/4 タスク、100%)。Session 11 では Phase 6.4 (`ranking_judge.py` 1016 行 → 4 ファイル分割) に進む。Phase 6.3 で導入した `AnthropicLike` Protocol / `FALLBACK_REASON_LABELS` public 集約 / `classify_api_exception` public / `compute_mu_for_monte_carlo` スカラー引数粒度の四位一体パターンが Phase 6.4 以降の設計の前提となる。

**push 状態**: 4 commit (`1d75ef0` + `ec789cd` + `6559e86` + `0f45545`) は user の `! git push origin main` で push 完了済 (Session 10 末尾、`10064c5..0f45545`)。
