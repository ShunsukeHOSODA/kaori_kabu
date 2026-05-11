# 引き継ぎ doc — 20260510-jquants-japan-stocks 完了 → 次回 A 案 (リスク指標 / ATR 日本株拡張)

**最終更新**: 2026-05-10（J-Quants v2 統合 + vs S&P500 比較 + Magic Formula 日本株対応 完了）
**前作業**: `.steering/20260510-13f-dynamic/handoff.md` (Phase D 完了)
**完了範囲**: Phase 1 (J-Quants v2 統合) + Phase 2 (vs ベンチマーク比較) + Phase 3 (Magic Formula 日本株対応)

---

## 1. 完了サマリー

### コミット履歴（9 件、新しい順）

| コミット | 内容 |
|---|---|
| `45ba09d` | docs(steering): 日本株 Magic Formula 実機検証スクショ追加 |
| `d2a5f0c` | feat(screener): 取引所 TO 選択時に日本株デフォルトティッカーへ自動切替 |
| `7c05d8d` | docs(steering): vs S&P500 ベンチマーク比較 実機検証スクショ追加 |
| `70e09ed` | feat(home): リスク指標パネルに vs S&P500 比較を統合 |
| `772c75f` | feat(risk-metrics): vs ベンチマーク比較指標 (α/β/IR/TE/Up-Down) + TDD 7 件 |
| `26e8b0b` | docs(steering): 20260510-jquants-japan-stocks 設計 doc 起票 |
| `d13480b` | docs(claude): §5 J-Quants Light の 12 週遅延制限を明記 |
| `2cb8ad6` | feat(home): 日本株 J-Quants v2 経路追加 + 12 週遅延 UI 明示 |
| `b6f9519` | feat(jquants): J-Quants v2 (API key 認証) クライアント + TDD 16 件 |

### Phase 1: J-Quants v2 クライアント実装

**発端**: 01_home.py 実機検証で 7203 (トヨタ) が EODHD で 404 → 原因調査の結果、**EODHD は日本株未対応**（`TO` は Toronto / `TSE/JP` は exchange code 自体存在せず）と判明。CLAUDE.md §5「J-Quants Light = 日本株の正本」整合のため J-Quants v2 を統合。

- `src/data/jquants.py`（新規 240 行）
  - `JQuantsClient` (frozen dataclass、EODHDClient パターン踏襲)
  - **v2 仕様**: `x-api-key` ヘッダ認証（v1 の refresh_token は 2025-12-22 以降廃止）、`/v2/equities/bars/daily` エンドポイント
  - 公開 API: `get_eod(code, *, from_date, to_date) → pd.DataFrame`
  - 純粋関数: `_normalize_code` (4 桁正規化: `7203/.T/.JP/72030` → `7203`) / `_normalize_v2_columns` (`O/H/L/C/Vo` → `Open/High/Low/Close/Volume`)
  - 例外階層: `JQuantsConfigError` / `JQuantsAuthError` / `JQuantsAPIError`
  - ParquetCache TTL 24h、Provenance attrs 6 キー、レート制限 60 req/min

- `src/config/settings.py`
  - `jquants_api_key: str` 新規追加（`JQUANTS_API_KEY`）
  - `jquants_refresh_token: str` は v1 deprecated として残置（破壊的変更回避）

- `src/dashboard/views/01_home.py`
  - `exchange == "JP"` 経路を J-Quants v2 にディスパッチ
  - `client` → `eodhd_client` リネーム（jquants_client と並ぶ命名）
  - JP 取得時は `to_date = today - 90日` に下げて Light プラン 12 週間遅延制限内に収める
  - `jp_used_delayed` フラグで「⚠️ 12 週間遅延データ表示中」UI alert 表示

- `data/holdings/portfolio.csv`: `7203,TO,...` → `7203,JP,...` 正規化

- `tests/unit/data/test_jquants.py`（新規 408 行、TDD 16 件 全 PASS）
  - TestNormalizeCode (5) / TestNormalizeV2Columns (2) / TestJQuantsClientConfig (1) / TestGetEOD (8: 基本 OHLCV / x-api-key ヘッダ / キャッシュ / Provenance / 期間指定 / 空レスポンス / 認証エラー / HTTP エラー)

**Light プラン制限の発見**:
- API レスポンスから `subscription covers: 2024-02-15 ~ 2026-02-15` 判明
- 公式は Free のみ「12 週間遅延」記載、Light は曖昧 → 実機検証で **Light も 12 週間遅延** と確定
- CLAUDE.md §5 のデータソース表を修正（commit `d13480b`）

### Phase 2: vs S&P500 ベンチマーク比較

**発端**: 「Sharpe 1.78 は高いの？低いの？」の相対判定不能。CLAUDE.md §9.4 シグナル根拠併記 / §9.7 認知バイアス対策（Recency Bias / Confirmation Bias）対応。

- `src/analysis/risk_metrics.py` 拡張（+148 行）
  - `BenchmarkMetadata` (frozen) — provenance 7 フィールド + `benchmark_label`
  - `BenchmarkComparison` (frozen) — α/β/IR/TE/Up Capture/Down Capture
  - `compute_benchmark_comparison(returns, benchmark_returns, *, benchmark_label, input_data_source) → BenchmarkComparison`
    - empyrical-reloaded: `ep.alpha` (Jensen 1968) / `ep.beta` / `ep.excess_sharpe` (IR Sharpe 1992 / Goodwin 1998) / `ep.up_capture` / `ep.down_capture`
    - **tracking_error は自前計算**: empyrical-reloaded に `tracking_error` 関数が無いため `std(R_p - R_b) × √252`
  - 共通日付 inner join、< 2 件で `ValueError`

- `tests/unit/analysis/test_risk_metrics.py` 拡張（+135 行、TDD 7 件 全 PASS）
  - TestComputeBenchmarkComparison: 完全相関_β1_α0 (変動系列で `Var(B)≠0` 確保) / β_0.5 / IR 数値 / Up-Down Capture / 共通日付なし_ValueError / metadata / frozen

- `src/dashboard/widgets/risk_metrics_panel.py` 拡張（+44 行）
  - `render_risk_metrics_panel(metrics, *, comparison=None, container=None)` — keyword-only `comparison` を後方互換で追加
  - 「📐 vs {benchmark_label}」サブヘッダ + 4+2 列グリッド + Provenance に学術根拠追記

- `src/dashboard/views/01_home.py` 統合
  - リスク指標計算後に SPY (EODHD) 取得 → `compute_benchmark_comparison` → `render_risk_metrics_panel(metrics, comparison=bench_cmp)`
  - SPY 取得失敗 (`EODHDAPIError / HTTPError / ValueError`) は捕捉して `bench_cmp=None` でフォールバック

**実機実測値** (`risk-metrics-vs-spy-verified.png`):
- α (年率) **+13.59%** / β **1.04** / IR 0.04 / TE 19.29%
- アップキャプチャ **104.1%** / ダウンキャプチャ **91.4%**
- → S&P500 を年率 +13.59% 上回り、上昇に乗り下落に強い理想的アクティブ運用パターン

### Phase 3: Magic Formula 日本株対応

**発端**: skill `magic-formula-screener` 完了チェックリスト「米国 + 日本両市場をカバー」未達成。J-Quants v2 が今日できた → ファンダ取得経路を整える。

**設計判断 (重要)**:
- J-Quants v2 で `/v2/fins/details` 試行 → **Light プランは 403** ("This API is not available on your subscription")
- `/v2/fins/statements` パスは v2 に存在せず（"endpoint does not exist"）
- → **J-Quants Light では日本株ファンダ取得不可** と確定
- 代替案 4 つを評価し **B: yfinance ファンダ補完** を採用
  - CLAUDE.md §5「yfinance（ファンダ補完）= 個人利用限定」と整合
  - 既存 `src/data/yfinance.py:build_screener_universe` が `.T` サフィックス対応で動作確認済み（実機 smoke で 7203 ebit=4.8 兆円取得成功）
  - Phase 3.3 で J-Quants Standard アップグレード時に置き換え可能

**実装**:
- `src/dashboard/views/02_screener.py` （+20 行 / -2 行）
  - 取引所 selectbox の help を「yfinance 経由で `.T` 形式に自動変換」明記
  - `_DEFAULT_TICKERS_US` (GAFAM 系) と `_DEFAULT_TICKERS_JP` (TOPIX Core30: 7203 6758 9984 6861 6098 8035 4063 6981 7974 8001) を分離
  - `exchange=="TO"` 選択時に textarea を日本株 default にスワップ (`key=f"ticker_input_{exchange}"`)
  - TO 選択時に 🇯🇵 キャプション追加
- コア実装は **既存ハイブリッド構成 (`yfinance fundamentals + EODHD prices`)** が日本株対応していたため変更不要

**実機実測値** (`japan-magic-formula-verified.png`):

| 順位 | ティッカー | 銘柄 | Composite | Q | V | R | 警告 |
|---|---|---|---|---|---|---|---|
| 1 | **6098** | リクルート | **59.5** | **100** | 39 | 75 | ✅ |
| 2 | 7974 | 任天堂 | 48.0 | 76 | 35 | 75 | ✅ |
| 3 | 6758 | ソニー | 44.0 | 56 | **64** | 35 | ⚠️ |
| 4 | **7203** | **トヨタ** | 33.2 | 43 | 58 | 11 | ⚠️ |
| 5 | 9984 | SoftBank G | 26.5 | 72 | 11 | 10 | ⚠️ |

---

## 2. 設計判断記録

### 採用

| 判断 | 理由 |
|---|---|
| J-Quants **v2** (API key 認証) | 2025-12-22 以降 v1 廃止、refresh_token → x-api-key 永続キー |
| 短縮カラム `O/H/L/C/Vo` → 長名展開 | 既存呼び出し側 (01_home.py / 02_screener.py) との互換性維持 |
| 4 桁証券コード正規化 (`_normalize_code`) | J-Quants API 入力は 4 桁、レスポンス Code は 5 桁（チェックデジット付き）の差分吸収 |
| `BenchmarkComparison` を `RiskMetrics` と別 dataclass | SRP（単一責務）— RiskMetrics は単一系列指標、Benchmark は 2 系列比較 |
| tracking_error は自前計算 (`std × √252`) | empyrical-reloaded に `tracking_error` 関数が存在しない |
| 日本株ファンダは yfinance | J-Quants Light は `/v2/fins/details` 非対応、CLAUDE.md §5「ファンダ補完」整合 |
| Light プラン 12 週間遅延を UI 明示 | 認知バイアス対策（Recency Bias 抑止）+ 透明性 |
| `client` → `eodhd_client` リネーム | `jquants_client` と並ぶ命名で曖昧性排除 |

### 後送り（次回タスク候補へ）

- リスク指標 / ATR の **日本株対応**（現状は `exchange=="JP"` の場合スキップ）→ **§4.1 A 案**
- HMM レジーム検出の VIX 代替パス → **§4.2 #2**
- Half-Kelly Decision Log 統合 → **§4.3 #3**
- Magic Formula 日本株対応の **J-Quants Standard 移行**（Phase 3.3）
- `06_macro.py` / `04_backtest.py` の本格実装（プレースホルダーのまま）

---

## 3. テストカバレッジサマリー

| ファイル | テスト件数 | 状態 |
|---|---|---|
| `tests/unit/data/test_jquants.py` | 16 件（新規） | ✅ 全 PASS |
| `tests/unit/analysis/test_risk_metrics.py` | 7 件（追加、既存 12 → 19） | ✅ 全 PASS |
| **全体 unit test** | **346 件 PASS** (本セッション +23) | ✅ |

---

## 4. 次回タスク候補（優先度順）

### 4.1 A 案: リスク指標 / ATR の **日本株対応** ⭐ 最優先（推奨）

**目的**: 01_home.py のリスク指標 / ATR セクションが現状 `exchange == "JP"` の銘柄をスキップしている。J-Quants v2 EOD 経路（既に実装済み）を統合して MVP #5 / #7 を「日本株でも動く」状態に。MVP β を **100% 完成** させる。

**所要時間**: 1.5h 想定

**実装範囲**:
1. `src/dashboard/views/01_home.py` のリスク指標計算ループ (line 336 付近):
   ```python
   # 現状: exchange == "JP" でスキップ
   if _h.exchange == "JP":
       continue
   ```
   → J-Quants v2 経路に分岐:
   ```python
   if _h.exchange == "JP":
       if jquants_client is None:
           continue  # API key 未設定なら skip
       jp_to = today - timedelta(days=90)  # Light プラン制限
       jp_one_year_ago = jp_to - timedelta(days=370)
       df_year = jquants_client.get_eod(v.ticker, from_date=jp_one_year_ago, to_date=jp_to)
       # JP は Close (大文字)、EODHD は close (小文字) の差分吸収
       prices_by_ticker[v.ticker] = pd.Series(
           df_year["Close"].astype(float).values,
           index=pd.to_datetime(df_year["Date"]),
           name=v.ticker,
       )
       continue
   ```

2. ATR セクション (line 405 付近) も同様に JP 経路追加:
   - J-Quants v2 の DataFrame は `High/Low/Close` 大文字
   - ATR 計算関数 `src/strategies/atr_stop.py` の入力フォーマット確認必要

3. **Note**: Light プラン 12 週遅延でも、過去 1 年 ATR / 過去 1 年リスク指標は **十分計算可能**（最新 90 日のみ欠落、252 営業日中 60 日くらい欠ける程度）。UI で「⚠️ JP データは最新 90 日除く」と alert 出す。

4. リスク指標ベンチマーク比較で **TOPIX を日本株ポートフォリオ向けに使う**選択肢:
   - SPY = 米国株ベンチマーク
   - 1306.JP（TOPIX 連動 ETF）= 日本株ベンチマーク
   - 混在ポートフォリオは S&P500 一本でも妥協可（実装は次フェーズ）

5. TDD: `tests/unit/data/test_jquants.py` に「過去 1 年取得」「OHLC カラム揃う」のスモークテスト追加（既存 16 件 + 2-3 件）

**検証手順**:
1. `pytest tests/unit/ --no-cov -m unit -q` → 346 + α 件 PASS
2. Streamlit + Playwright で 01_home → 最新評価 → リスク指標セクションに 7203 トヨタも反映されているか確認
3. ATR アラートに 7203 が現れるか確認（現状 1 銘柄 AAPL のみ）
4. スクショ証跡 `.steering/20260510-jquants-japan-stocks/risk-atr-japan-verified.png`

### 4.2 #2: HMM VIX 代替パス（1h）

VIX 取得不可時のフォールバック実装。Crisis 判定の信頼性を底上げ。
- 現状は EODHD VIX 一本依存、`EODHDAPIError` で None フォールバック
- 代替: SPY の rolling 30 日 std × √252 を VIX 代理として使う（簡易だが連続性確保）

### 4.3 #3: Half-Kelly Decision Log 統合（1h）

「なぜこの数量を買ったか」の Provenance 強化。
- `src/portfolio/decision_log.py` に `kelly_recommendation` フィールド追加
- 02_screener.py で買い候補に Kelly 推奨サイズを併記
- BUY 時の Decision Log に Kelly metadata を自動付与

### 4.4 Phase 3.3 候補（中期）

- J-Quants Standard プラン (+1,650 円/月) へアップグレード → 当日データ + `/v2/fins/details` (財務諸表) で日本株 Magic Formula を J-Quants 正本化
- vectorbt + QuantStats バックテスト (`04_backtest.py`) の本格実装
- Polymarket / FRED 完全統合 (`06_macro.py`)
- Fama-French 5-factor 帰因分析
- EDINET / e-Stat / 日銀 マクロデータ統合

---

## 5. 既知の課題

### 5.1 J-Quants Light の 12 週遅延（仕様）

最新 90 日のデータが取れない。UI alert で明示済み。Standard プランで解消。

### 5.2 リスク指標 / ATR が JP 銘柄スキップ中

→ **§4.1 A 案で解決**

### 5.3 yfinance ファンダの規約グレー

CLAUDE.md §5「個人利用限定」前提で許容、Phase 3.3 で J-Quants Standard へ置き換え予定。

### 5.4 EODHD `client` 残存箇所

01_home.py の `_detect_market_regime_cached()` 関数内 (line 79) は **ローカル変数の `client`** で問題なし。グローバル `client` 残存は完全に除去済み。

### 5.5 .gitignore の `screener-*.png` ルール

検証スクショを `screener-*.png` 命名すると ignore される。**`japan-magic-formula-verified.png` 形式で接頭辞回避**。

### 5.6 13F-NT (守秘要請) UI 表示分岐（前回 handoff から残存）

`src/data/sec_edgar.py` で 13F-NT を `EDGARNotFoundError` 一括処理。`form == "13F-NT"` で別メッセージ「守秘要請中」を出すと UX 向上。

---

## 6. ファイル変更サマリ

| ファイル | 変更内容 |
|---|---|
| `src/data/jquants.py` | **新規** 240 行（v2 クライアント） |
| `src/config/settings.py` | `jquants_api_key` フィールド追加（+3 行） |
| `src/dashboard/views/01_home.py` | JP 経路ディスパッチ + 12 週遅延 alert + S&P500 ベンチマーク統合（+74 / -5 行 + 別 commit +33 行） |
| `data/holdings/portfolio.csv` | `7203,TO` → `7203,JP`（1 行修正、untracked） |
| `CLAUDE.md` | §5 J-Quants Light の 12 週遅延制限明記（1 行修正） |
| `src/analysis/risk_metrics.py` | `BenchmarkMetadata` / `BenchmarkComparison` / `compute_benchmark_comparison` 追加（+148 行） |
| `src/dashboard/widgets/risk_metrics_panel.py` | vs ベンチマーク行 + Provenance 拡張（+44 / -1 行） |
| `src/dashboard/views/02_screener.py` | TO 選択時の日本株デフォルトティッカー切替（+20 / -2 行） |
| `tests/unit/data/test_jquants.py` | **新規** 408 行（TDD 16 件） |
| `tests/unit/analysis/test_risk_metrics.py` | `TestComputeBenchmarkComparison` 7 件追加（+135 行） |
| `.steering/20260510-jquants-japan-stocks/design.md` | **新規** 192 行（設計記録） |
| `.steering/20260510-jquants-japan-stocks/risk-metrics-vs-spy-verified.png` | 検証スクショ |
| `.steering/20260510-jquants-japan-stocks/japan-magic-formula-verified.png` | 検証スクショ |
| `.steering/20260510-jquants-japan-stocks/handoff.md` | **新規**（本ファイル） |

**合計**: 7 ファイル新規 / 8 ファイル修正、コミット 9 件、insertions ~1,400 行

---

## 7. CLAUDE.md 規約適合チェック

- [x] §1 米国 + 日本両市場対応（MF #1 達成、#5/#7 は §4.1 で対応予定）
- [x] §5 J-Quants Light 表記を実態（12 週遅延）に修正
- [x] §6 出力先固定: `.steering/20260510-jquants-japan-stocks/{design,handoff}.md`
- [x] §7 1 ファイル毎承認ゲート: コミット 9 件で論理単位分割
- [x] §9.1 Decimal: 金額は Decimal、OHLC は float（UI 直前に Decimal 化）
- [x] §9.2 キャッシュ: `data/cache/JQUANTS/eod_jp_*.parquet`、TTL 24h
- [x] §9.4 シグナル根拠併記: vs S&P500 比較で「Sharpe 1.78 は高いか低いか」明示可能に
- [x] §9.7 認知バイアス警告: 12 週遅延 alert + Recency Bias / Confirmation Bias caption
- [x] §9.8 Provenance: source/fetched_at/endpoint/params_hash/cache_hit/cache_age_sec + benchmark_label 全付与
- [x] §11 安全装置: API キーは `.env` のみ、例外メッセージに含めない
- [x] §12 テスト: pytest **346 件 PASS**、新規ファイル全カバー

---

## 8. 検証スクショ証跡

| ファイル | 内容 |
|---|---|
| `.steering/20260510-jquants-japan-stocks/risk-metrics-vs-spy-verified.png` | 01_home リスク指標 + vs S&P500 比較フル表示（α +13.59% / β 1.04 / Up 104% / Down 91%）|
| `.steering/20260510-jquants-japan-stocks/japan-magic-formula-verified.png` | 02_screener 東証選択 + 日本株 10 銘柄 Magic Formula + Composite Score 7 軸（6098 リクルート首位 59.5、トヨタ 33.2 等） |
| `home-jquants-v2-7203-verified.png` (root、untracked) | 01_home 最新評価で 7203 トヨタ JPY 直接表示 +33.18% 利益 |
| `home-mvp-5-6-7-verified.png` (root、untracked) | 01_home MVP #5/#6/#7 全表示確認（前 stage）|

---

## 9. 次セッション開始用プロンプト

次セッション開始時、ユーザーは以下を Claude に投げる:

```
.steering/20260510-jquants-japan-stocks/handoff.md §4.1 A 案
（リスク指標 / ATR の日本株拡張）を進めて。

事前読み込み:
- .steering/20260510-jquants-japan-stocks/handoff.md (本ファイル §4.1)
- .steering/20260510-jquants-japan-stocks/design.md
- src/dashboard/views/01_home.py (line 336-450 周辺の JP スキップ箇所)
- src/data/jquants.py (既存 JQuantsClient.get_eod)
- src/strategies/atr_stop.py (ATR 計算関数の入力フォーマット)

実装方針:
- TDD で進める
- 既存 J-Quants v2 経路 (eod_jp_*.parquet キャッシュ) を再利用
- リスク指標は JP 過去 1 年（最新 90 日除く）で計算、UI 明示
- ATR も同様に JP 過去 90 日（最新 90 日除く）で計算
- Playwright で実機検証 → スクショ `.steering/.../risk-atr-japan-verified.png`
- コミット規約: 既存パターン踏襲（[20260510-jquants-japan-stocks] スコープ継続）

承認後に着手。
```
