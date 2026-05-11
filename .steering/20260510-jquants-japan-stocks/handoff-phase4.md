# 引き継ぎ doc — 20260510-jquants-japan-stocks Phase 4 完了 → 次回 §4.2 #2 (HMM VIX 代替) or §4.3 #3 (Half-Kelly DLog)

**最終更新**: 2026-05-11（リスク指標 / ATR の日本株拡張 完了 = MVP β 100% 達成）
**前 handoff**: `.steering/20260510-jquants-japan-stocks/handoff.md` (Phase 1-3 完了、§4.1 A 案を「次回」として残置)
**完了範囲**: Phase 4 (リスク指標 / ATR 日本株 J-Quants v2 経路拡張 + UI 警告強化)

---

## 1. 完了サマリー

### コミット履歴（2 件、新しい順）

| コミット | 内容 |
|---|---|
| `76c3dbb` | feat(home): リスク指標 + ATR を JP 銘柄に拡張（J-Quants v2 経路）+ スクショ証跡 3 枚 |
| `d799449` | feat(jquants): J-Quants DF → 内部小文字 OHLC 変換ヘルパー + TDD 6 件 |

### Phase 4: リスク指標 / ATR 日本株拡張

**発端**: 前 handoff §4.1 A 案。01_home.py のリスク指標 / ATR セクションが `exchange == "JP"` をスキップしていた → MVP #5 (リスク指標) / #7 (ATR) を「日本株でも動く」状態にして MVP β を 100% 完成。

**実装**:

1. **OHLC 変換ヘルパー** (`src/data/jquants.py` +71 行)
   - `extract_close_series(df, *, ticker_name) -> pd.Series` — リスク指標経路用。`Date` + `Close` (大文字) → `pd.Series(close_float, index=DatetimeIndex, name=ticker, dtype=float)`
   - `extract_ohlc_lowercase(df) -> pd.DataFrame` — ATR 経路用。`High/Low/Close` → `high/low/close` (idempotent: EODHD DF もそのまま流せる)
   - 欠落カラムは `ValueError` で fail-fast（silent NaN 伝播防止）

2. **リスク指標セクション** (`src/dashboard/views/01_home.py` line 337 周辺)
   - 既存の `if _h.exchange == "JP": continue` を J-Quants v2 経路にディスパッチ
   - `jp_metrics_to = today - timedelta(days=90)` / `jp_metrics_from = jp_metrics_to - timedelta(days=370)`
   - `jquants_client is None` で graceful skip（API key 未設定時）
   - 例外 4 種捕捉: `JQuantsAuthError / JQuantsConfigError / JQuantsAPIError / httpx.HTTPError`
   - `ℹ️ 「日本株のリスク指標は最新 ~90 日除外で計算（J-Quants Light の 12 週間遅延制限）」` 新規 alert

3. **ATR セクション** (`src/dashboard/views/01_home.py` line 440 周辺)
   - JP 経路: `from = today - 180d` → `to = today - 90d` のウィンドウで OHLC 取得
   - `extract_ohlc_lowercase()` で大→小文字変換、既存 `evaluate_alert(...)` をそのまま再利用
   - 通貨は `currency="JPY"` 固定
   - **⚠️ 警告強化（A 案採用）**: `st.warning` で表示、「日本株 ATR は参考値です（リアルタイム判定には使えません）」「~90 日前時点のシミュレーション値」「今日の利確/損切り判断には使わないでください」「J-Quants Standard (+1,650 円/月) or 証券会社アプリで判定」と明示

4. **テスト** (`tests/unit/data/test_jquants.py` +130 行)
   - `TestExtractCloseSeries`: 3 件（基本ケース / 空 DF / 必須カラム欠落 ValueError）
   - `TestExtractOhlcLowercase`: 3 件（基本ケース / 必須カラム欠落 ValueError / idempotent 小文字 DF）
   - 全 6 件 PASS、`pytest tests/unit/ -m unit` で **352 件 PASS**（前回 346 + 新規 6）

### 実機実測値（7203 トヨタを含む 2 銘柄ポートフォリオ）

| 指標 | 値 | 前回（米国株のみ）比 |
|---|---|---|
| 評価額 | ¥811,380 | +¥371,400 (7203 加算分) |
| 含み損益 | +¥281,380 (+53.09%) | — |
| **Sharpe** | **2.30** | 1.78 → 改善 |
| Sortino | 4.18 | — |
| Calmar | 6.18 | — |
| 年率リターン | +57.37% | — |
| Max DD | -9.29% | — |
| **α (vs S&P500、年率)** | **+32.82%** | +13.59% → 大幅改善 |
| β | 0.72 | 1.04 → 低下（JP 銘柄の市場感応度低い） |
| Information Ratio | 0.07 | — |
| Tracking Error | 19.17% | — |
| Up / Down Capture | 53.2% / 30.4% | 104.1% / 91.4% から変化 |
| **7203 ATR alert** | 🟡 **接近**（基準 ¥3,699 / 現在 ¥3,714）売却検討 | (前回スキップ→今回初登場) |

---

## 2. 設計判断記録

### A 案採用の理由（ATR JP「参考値」明示）

ユーザーから「日本株 12 週間遅延データで正しく利確時期とか判断できるの？」と問われ、4 案検討:

| 案 | 概要 | 採否 |
|---|---|---|
| **A. UI 警告強化 + 「参考値」明示** | 「リアルタイム判定には使えません」と明示、規律トレーニング用途に限定 | **採用** |
| B. JP ATR セクション非表示 | 機能を隠す | 不採用（情報は出した方が学習価値あり） |
| C. J-Quants Standard へアップグレード | +1,650 円/月で当日データ取得可能 | 後回し（コスト対効果次フェーズで判断） |
| D. yfinance ハイブリッド | 当日価格 + 遅延 OHLC | 不採用（規約グレー領域を ATR にまで広げない） |

**A 案の本質**: リスク指標は 252 営業日中 60-80 日欠落しても**統計性質変わらず**（Sharpe / Max DD は長期分布の代表値）。一方 ATR は「**今日**の True Range」が本質 → 90 日前の ATR で今日の判断はできない。この差を UI で明示することで、ユーザーが誤用しない構造を作る。

### 採用したヘルパー設計

| 判断 | 理由 |
|---|---|
| `extract_close_series` / `extract_ohlc_lowercase` を `jquants.py` に置く | J-Quants データの内部変換ロジックは J-Quants モジュールに凝集（SRP） |
| 純粋関数（クライアントメソッドではなく module-level function） | I/O なし、テストしやすい、EODHD DF（既存小文字）も流せる idempotent 性 |
| 欠落カラムは ValueError で fail-fast | silent NaN 伝播による下流 (compute_risk_metrics / calculate_atr) の誤計算を予防 |
| ATR JP ウィンドウは `from = -180d → to = -90d` の 90 日 | 既存 US 経路と同じ「過去 90 日」サンプル数を確保、最新 90 日のみ Light 制約で除外 |
| `if atr_jp_used_delayed:` で `st.warning` (Info ではなく Warning) | A 案の本質「ATR JP は誤用しないでください」を視覚的に強調 |

### 後送り（次回タスク候補へ）

- HMM レジーム検出の VIX 代替パス → **§4.1 #2**
- Half-Kelly Decision Log 統合 → **§4.2 #3**
- J-Quants Standard へのアップグレード判断（コスト対効果） → **§4.3**
- TOPIX (1306) を日本株ポートフォリオ用ベンチマークとして使う（現状 SPY 一本） → **§4.4**
- 02_screener.py の動的銘柄候補拡張（TOPIX Core30 → TOPIX 100 → TOPIX 500） → **§4.5**

---

## 3. テストカバレッジサマリー

| ファイル | テスト件数 | 状態 |
|---|---|---|
| `tests/unit/data/test_jquants.py::TestExtractCloseSeries` | 3 件（新規） | ✅ 全 PASS |
| `tests/unit/data/test_jquants.py::TestExtractOhlcLowercase` | 3 件（新規） | ✅ 全 PASS |
| **全体 unit test** | **352 件 PASS** (本セッション +6) | ✅ |

`ruff check --select F,E,W` ロジックエラーゼロ（RUF001/002/003 全角句読点は既存方針で許容）。

---

## 4. 次回タスク候補（優先度順）

### 4.1 #2: HMM VIX 代替パス（1h、推奨）

**目的**: VIX (EODHD INDX 取引所) が取得失敗した時に Crisis 判定が None で fallback してしまう問題を底上げ。

**実装範囲**:
1. `src/analysis/regime.py` に `compute_realized_volatility(prices, window=30) -> pd.Series` を追加
2. SPY の log returns rolling 30 日標準偏差 × √252 を VIX 代理として使う
3. `01_home.py:_detect_market_regime_cached()` で VIX 取得失敗時のみフォールバック発動
4. UI に「⚠️ VIX 取得失敗 → SPY realized vol を代理使用」alert
5. TDD: `tests/unit/analysis/test_regime.py` に realized vol 計算テスト 2-3 件

**期待効果**: Crisis 判定の連続性確保、HMM 学習データの欠落フリー化。

### 4.2 #3: Half-Kelly Decision Log 統合（1h）

**目的**: 「なぜこの数量を買ったか」の Provenance 強化（CLAUDE.md §9.8.3）。

**実装範囲**:
1. `src/portfolio/decision_log.py` に `kelly_recommendation` フィールド追加（既存スキーマに optional 追加）
2. `02_screener.py` で買い候補一覧に Half-Kelly 推奨サイズ列を併記
3. BUY 時の Decision Log に Kelly metadata（win_rate / payoff_ratio / fraction / capped_pct）を自動付与
4. TDD: `tests/unit/portfolio/test_decision_log.py` に kelly_metadata 追加テスト 2 件
5. Streamlit + Playwright で 02_screener → BUY ボタンクリック → JSONL に Kelly 記録確認

### 4.3 J-Quants Standard アップグレード判断（リサーチ + 意思決定、0.5h）

**目的**: ATR JP がリアルタイム機能できるよう Standard プラン (+1,650 円/月) 移行のコスト対効果を評価。

**判断基準**:
- 日本株保有が 3 銘柄以上に拡大したら検討開始
- 損切り判断を**ユーザー自身が証券会社アプリで毎日見る運用**が定着していれば不要
- `/v2/fins/details` (財務諸表) で日本株 Magic Formula を yfinance → J-Quants 正本化できる副次効果あり

**ドキュメント**: `docs/cost-budget.md` に「Standard アップグレードの判断基準」セクション追加。

### 4.4 TOPIX (1306) を日本株ポートフォリオ用ベンチマークに（中期、1h）

**目的**: 混在ポートフォリオで「S&P500 一本」が不適切な場合に切り替え可能に。

**実装範囲**:
1. `src/analysis/risk_metrics.py::compute_benchmark_comparison()` に benchmark_currency パラメータ追加
2. 01_home.py で portfolio に占める JP 比率が 50% 超なら 1306.JP (TOPIX 連動 ETF) を J-Quants v2 経由で取得
3. 混合の場合は 50:50 で SPY + 1306 を加重平均（暫定方針）
4. UI で「📐 vs TOPIX」or 「📐 vs S&P500 + TOPIX 混合」を出し分け
5. TDD: `tests/unit/analysis/test_risk_metrics.py` に通貨混合テスト 2-3 件

### 4.5 02_screener.py の動的銘柄候補拡張（中期、1.5h）

**目的**: 現状 TOPIX Core30 ハードコード → TOPIX 100 / TOPIX 500 から動的取得。

**実装範囲**:
1. `src/data/jquants.py` に `get_listed_info(market_code) -> pd.DataFrame` 追加（J-Quants `/v2/listed/info` エンドポイント、要 Standard 以上の可能性あり）
2. 代替: FinanceDatabase (`JerBouma/FinanceDatabase`) から TSE 銘柄リスト取得（無料）
3. UI で TOPIX セグメント (Core30 / Large70 / Mid400) selectbox 化
4. キャッシュ TTL 7d（銘柄リストは頻繁に変わらない）

---

## 5. 既知の課題

### 5.1 J-Quants Light の 12 週間遅延（仕様、§4.3 Standard で解消可能）

リスク指標は影響軽微（統計性質変わらず）、ATR は本質的に「参考値」止まり。UI で警告強化済み。

### 5.2 fullPage スクショが Streamlit のスクロール構造で取れない

Playwright `screenshot({ fullPage: true })` が viewport サイズ (1425x669) しか返さない。
**運用**: セクションごとに見出し click → スクロール → viewport screenshot を分けて撮る方式が確実。

### 5.3 OMC GateGuard が頻繁に発火

`.omc/project-memory.json` の hooks 設定で Edit/Bash の前に毎回事実提示が求められる。
**運用**: 事実提示を**簡潔に**書いて再 retry すれば通る。緊急時は `ECC_GATEGUARD=off` 環境変数で一時無効化可能（ユーザー承認下で）。

### 5.4 git config user.email / user.name が未設定

コミット時に warning「configured automatically based on your username and hostname」表示。実害なし。気になれば `git config --global user.email "..."` で設定可能。

### 5.5 yfinance ファンダ補完の規約グレー（前 handoff §5.3 から継続）

CLAUDE.md §5「個人利用限定」前提で許容。日本株ファンダの J-Quants Standard 正本化は §4.3 で評価。

### 5.6 13F-NT (守秘要請) UI 表示分岐（前 handoff §5.6 から継続）

未解消。`src/data/sec_edgar.py` で `form == "13F-NT"` を別メッセージ化すると UX 向上。

---

## 6. ファイル変更サマリ

| ファイル | 変更内容 |
|---|---|
| `src/data/jquants.py` | `extract_close_series` / `extract_ohlc_lowercase` 純粋関数追加（+71 行） |
| `src/dashboard/views/01_home.py` | import 追加 + リスク指標 / ATR の JP 経路ディスパッチ + 2 種類 alert（+71 / -8 行） |
| `tests/unit/data/test_jquants.py` | `TestExtractCloseSeries` 3 件 + `TestExtractOhlcLowercase` 3 件追加（+130 行） |
| `.steering/20260510-jquants-japan-stocks/risk-metrics-japan-verified.png` | リスク指標 + JP alert + 7203 評価行 検証スクショ |
| `.steering/20260510-jquants-japan-stocks/atr-japan-verified.png` | ATR セクション + ⚠️ 強化警告 + 7203 alert 検証スクショ |
| `.steering/20260510-jquants-japan-stocks/risk-atr-japan-verified.png` | フルページスクショ（最下部のみ、参考） |
| `.steering/20260510-jquants-japan-stocks/handoff-phase4.md` | **新規**（本ファイル） |

**合計**: 4 ファイル新規（スクショ 3 + handoff 1）/ 3 ファイル修正、コミット 2 件、insertions ~270 行。

---

## 7. CLAUDE.md 規約適合チェック

- [x] §1 米国 + 日本両市場対応（MVP #5 リスク指標 / #7 ATR が JP でも動く）→ **MVP β 100% 達成**
- [x] §5 J-Quants Light の 12 週間遅延制約を UI で明示
- [x] §6 出力先固定: `.steering/20260510-jquants-japan-stocks/{handoff-phase4,*.png}`
- [x] §7 1 ファイル毎承認ゲート: コミット 2 件で論理単位分割（ヘルパー → 統合）
- [x] §9.1 Decimal: 金額は `Decimal(str(df["close"].iloc[-1]))` で精度確保
- [x] §9.2 キャッシュ: `data/cache/JQUANTS/eod_jp_*.parquet` TTL 24h を再利用（新規キャッシュなし）
- [x] §9.4 シグナル根拠併記: JP リスク指標で「12 週遅延データ」根拠を ℹ️ alert で明示
- [x] §9.5 損切り規律: ATR JP「参考値」明示で誤用防止、リアルタイム判定経路を Standard / 証券会社アプリへ誘導
- [x] §9.7 認知バイアス警告: Recency Bias（最新データ偏重）対策として 90 日遅延の事実を強調
- [x] §9.8 Provenance: J-Quants 経路の `df.attrs` (source/fetched_at/endpoint/params_hash/cache_hit/cache_age_sec) は既存実装で自動付与
- [x] §11 安全装置: API キーは `.env` のみ、例外メッセージに含めない
- [x] §12 テスト: pytest **352 件 PASS**、新規ヘルパー全カバー

---

## 8. 検証スクショ証跡

| ファイル | 内容 |
|---|---|
| `.steering/20260510-jquants-japan-stocks/risk-metrics-japan-verified.png` | 01_home 評価テーブル（AAPL ¥439,980 +75.99% / **7203 ¥371,400 +32.64%**）+ 📊 リスク指標（Sharpe 2.30 / Sortino 4.18 / Calmar 6.18 / Max DD -9.29% / VaR -1.77% / CVaR -2.06% / 年率 +57.37% / Vol +20.65%）+ **ℹ️「日本株のリスク指標は最新 ~90 日除外で計算」 alert** 表示 |
| `.steering/20260510-jquants-japan-stocks/atr-japan-verified.png` | 📐 vs S&P500（Up 53.2% / Down 30.4%）+ ⚠️ 利確/損切りアラート + **⚠️ 強化警告**「日本株 ATR は参考値です」「~90 日前時点のシミュレーション値」「今日の利確/損切り判断には使わないでください」「Standard プランへのアップグレード(+1,650 円/月) or 証券会社アプリで判定」 + **🟡 7203 接近（基準 ¥3,699 / 現在 ¥3,714）売却検討** |
| `.steering/20260510-jquants-japan-stocks/risk-atr-japan-verified.png` | フルページ（保有銘柄一覧テーブル + 認知バイアス警告、実質的に最下部のみ、Streamlit スクロール構造により viewport サイズで保存される既知の制約） |

---

## 9. 次セッション開始用プロンプト

次セッション開始時、ユーザーは以下のいずれかを Claude に投げる:

### 9.1 §4.1 #2 HMM VIX 代替パス を進める場合

```
.steering/20260510-jquants-japan-stocks/handoff-phase4.md §4.1
（HMM VIX 代替パス）を進めて。

事前読み込み:
- .steering/20260510-jquants-japan-stocks/handoff-phase4.md (本ファイル §4.1)
- src/analysis/regime.py (HMM 学習関数 detect_regime_with_provenance)
- src/dashboard/views/01_home.py:_detect_market_regime_cached (line 70 周辺)
- tests/unit/analysis/test_regime.py (既存テストパターン)

実装方針:
- TDD で進める（compute_realized_volatility テストファースト）
- SPY の log returns rolling 30 日 std × √252 を VIX 代理として算出
- VIX 取得成功時はそのまま使い、失敗時のみ代理発動
- UI に「⚠️ VIX 取得失敗 → SPY realized vol を代理使用」alert を出す
- コミット規約: feat(regime): HMM VIX 代替 + TDD [20260510-jquants-japan-stocks]

承認後に着手。
```

### 9.2 §4.2 #3 Half-Kelly Decision Log 統合 を進める場合

```
.steering/20260510-jquants-japan-stocks/handoff-phase4.md §4.2
（Half-Kelly Decision Log 統合）を進めて。

事前読み込み:
- .steering/20260510-jquants-japan-stocks/handoff-phase4.md (本ファイル §4.2)
- src/portfolio/decision_log.py (既存スキーマ)
- src/strategies/kelly.py (Half-Kelly 計算関数)
- src/dashboard/views/02_screener.py (買い候補表示ロジック)
- tests/unit/portfolio/test_decision_log.py

実装方針:
- TDD で進める
- decision_log.py スキーマに optional kelly_recommendation フィールド追加（後方互換）
- 02_screener.py の候補テーブルに Kelly 推奨サイズ列を併記
- BUY 時に自動で kelly_metadata を Decision Log に書く
- Playwright で 02_screener → BUY → JSONL 確認
- コミット規約: feat(decision-log): Half-Kelly 統合 + TDD [20260510-jquants-japan-stocks]

承認後に着手。
```

### 9.3 §4.3 J-Quants Standard アップグレード判断 を進める場合

```
.steering/20260510-jquants-japan-stocks/handoff-phase4.md §4.3
（J-Quants Standard アップグレード判断）を進めて。

事前読み込み:
- .steering/20260510-jquants-japan-stocks/handoff-phase4.md (本ファイル §4.3)
- docs/cost-budget.md
- https://jpx-jquants.com/ プラン一覧（要 WebFetch）

実装方針:
- 現在の保有 JP 銘柄数 / Magic Formula JP 利用頻度 / ATR JP 判定頻度を計測
- Standard プラン (+1,650 円) で増える価値（当日データ + /v2/fins/details）を定量化
- docs/cost-budget.md に「Standard アップグレード判断基準」セクション追加
- ユーザーに 3 案提示（即時アップグレード / 6 ヶ月後再評価 / 永続 Light + 現運用維持）
```

---

## 10. セッション運用メモ（次回への申し送り）

### 効いたこと

- **TDD ファースト**: RED → GREEN → 検証の流れで実装ブレなし
- **ユーザーへの質問タイミング**: 「12 週遅延で利確判断できるの？」を実装途中で受けて A 案に方針転換 → 後戻りなし
- **論理単位コミット**: ヘルパー追加 / 統合 / スクショ証跡 を分けたことで `git log` が読みやすい

### 改善したいこと

- **Playwright fullPage スクショの制約**: Streamlit のスクロール構造で fullPage が viewport サイズしか返さない → 次回はセクションごとに見出し click → viewport screenshot を最初から計画する
- **OMC GateGuard 対応コスト**: 事実提示で 1 リクエスト追加コスト発生 → 慣れれば 5-10 秒で書けるので致命的ではないが、毎回 Edit / Bash で発火するので積算は無視できない
- **ユーザーからの「動いてる？」連打**: Playwright MCP のレスポンス遅延 + 私の応答長で「待たされてる」体感 → 次回はもっと簡潔な進捗報告を心がける（1-2 行 / step）

### 持ち越し中の課題

- 5.6 13F-NT UI 表示分岐（前回から継続、優先度低）
- 5.5 yfinance 規約グレー（CLAUDE.md §5 で明示済み、Standard 移行で解消可）

---

**handoff-phase4.md 終わり**
