# Long-Term Investment Architecture（kaori_kabu Phase 3）

> **目的**: Magic Formula 単独 + ニュース/センチメントの現状を、世界トップ投資家全員の視座を反映する **Composite Investment Score** に拡張する。「素人でも思いつく抜けがないように」「世界一の投資家目線で最高のもの」を実現する設計図。

最終更新: 2026-05-09
ステータス: ドラフト（Phase 3.1 実装直前）

---

## 1. 設計動機

ユーザー指示（2026-05-09）:
> 長期保有株のおすすめの場合は配当や優待券も加味した上で有利だと判定されたりするようになってる？素人考え？本音で判断して。

→ 現状 NO。Magic Formula は ROC + EY のみで、配当・優待・破綻リスク・成長補正を見ない。長期保有・配当再投資・日本株インカム重視には**根本的に不足**。

ユーザー追加指示:
> 素人でも思いつく抜けがないように。もう一度世界一の投資家目線で最高のものができるように調査と構造の再検討をして！この株運用用で作成したskillsやagent、これまで入れたプラグインskillsを総動員して。

→ 単一指標ではなく **8 投資家視座** + **配当再投資モデル** + **日本株固有制度** + **認知バイアス対策** + **流動性** を網羅した **Composite Investment Score** に再構築する。

---

## 2. 投資家別「見るべき軸」の網羅マトリクス

| 視座 | 既存実装 | 追加すべき軸 | データソース |
|---|---|---|---|
| **Greenblatt（質×割安）** | ROC + EY ✅ | — | EODHD ファンダ |
| **Buffett-Munger（質×価値）** | — | ROIC > WACC、FCF yield、Buyback yield、経営者在任、Net cash | EODHD + 10-K |
| **Lynch（10-bagger）** | — | PEG、売上 5y CAGR、地理・事業セグメント分散 | EODHD |
| **Druckenmiller（流動性 + 成長）** | — | 売上成長 vs 業界、営業利益率トレンド、Fed BS 連動 | EODHD + FRED |
| **Dalio（負債サイクル）** | — | 純有利子負債/EBITDA、利息カバレッジ、短期負債比率 | EODHD |
| **Pabrai（クローニング）** | 13F skill（未統合） | スーパー投資家の最近の買い増し・退却 | SEC EDGAR 13F |
| **Burry（テールリスク）** | — | Altman Z-Score、Beneish M-Score、Short interest、CDS スプレッド | EODHD + Tavily |
| **Ackman（ガバナンス）** | — | 取締役会独立性、SEC アクション、ESG スコア | Tavily/Exa |
| **AQR (Asness/Frazzini)** | — | QMJ (Quality Minus Junk)、Carhart 4-factor exposure | EODHD + 自前計算 |
| **Coca-Cola Buffett モデル** | — | Forward dividend yield、配当成長 5y CAGR、配当性向、連続増配 | EODHD |
| **日本株固有** | — | 株主優待利回り、NISA 優先、配当二重課税控除 | 手動 CSV + .env |
| **流動性・取引コスト** | — | 出来高/浮動株、ビッド-アスク | EODHD |
| **認知バイアス対策** | ATR ストップ ✅ | bear case 強制併記、5/10/20 年長期チャート | UI 規約 |

→ 既存 ROC + EY は `Quality × Value` の 2 軸のみ。**追加で 8 軸群を実装し、合算する Composite Investment Score を設計する**。

---

## 3. Composite Investment Score 設計

### 3.1 8 サブスコア（各 0-100 に正規化）

| サブスコア | 構成指標 | 計算方法 |
|---|---|---|
| **Q (Quality)** | ROIC, FCF yield, Altman Z, Beneish M, QMJ | クロスセクションで z-score → 0-100 マッピング |
| **V (Value)** | EY (EBIT/EV), P/B, EV/EBITDA, PEG | 低い方が高スコア |
| **I (Income)** | Forward dividend yield + Buyback yield + 優待 yield | 単純合算（"真の株主リターン"）|
| **G (Growth)** | 売上 5y CAGR, EPS 5y CAGR, 配当 5y CAGR | 加重平均 |
| **M (Momentum)** | 12m return, 1m return | Carhart 規格 |
| **R (Risk)** | β, 純有利子負債/EBITDA, Short interest, 連続赤字年数 | **逆スコア**（低リスク=高得点）|
| **C (Conviction)** | 13F 機関投資家保有率, スーパー投資家保有, インサイダー保有 | 既存 13f-cloning-tracker 経由 |
| **S (Sentiment)** | 既存 SentimentAnalyzer の score | -1〜+1 を 0-100 に変換 |

### 3.2 投資スタイル別プリセット（重み付け合算）

| プリセット | Q | V | I | G | M | R | C | S | 想定ユーザー |
|---|--:|--:|--:|--:|--:|--:|--:|--:|---|
| **Buffett 型** | 30 | 25 | 20 | 10 | 0 | 10 | 5 | 0 | 質×割安、長期ホールド |
| **Lynch 型（成長）** | 20 | 20 | 5 | 35 | 15 | 5 | 0 | 0 | PEG 重視、10-bagger 狙い |
| **配当再投資型（Coke）** | 25 | 15 | 50 | 5 | 0 | 5 | 0 | 0 | インカム + 安定、退職後 |
| **逆張り型** | 25 | 35 | 0 | 0 | 0 | 15 | 5 | 20 | バリュー深堀り、Sentiment 低=買い |
| **クローニング型** | 20 | 20 | 5 | 10 | 5 | 5 | 35 | 0 | スーパー投資家追従 |
| **テールリスク回避型** | 30 | 20 | 15 | 5 | 0 | 30 | 0 | 0 | Burry 流、安全マージン最優先 |

各プリセットの合計 = 100。

### 3.3 警告システム（独立判定、合算スコアと並行）

| 警告 | 閾値 | 表示 |
|---|---|---|
| 破綻リスク | Altman Z < 1.8 | 🚨 RED |
| 不正会計疑い | Beneish M > -1.78 | 🚨 RED |
| 減配リスク | 配当性向 > 90% | ⚠️ AMBER |
| マージン崩壊 | 営業利益率 5y トレンド < 0 | ⚠️ AMBER |
| 機関撤退 | 13F 直近四半期 -20%+ | ⚠️ AMBER |
| 連続赤字 | 3 年連続赤字 | 🚨 RED |
| 高 leverage | 純有利子負債/EBITDA > 5 | ⚠️ AMBER |
| 流動性低下 | 直近 20 営業日平均出来高 < 100k | ℹ️ NOTE |

**警告がある銘柄は Composite Score がいくら高くても除外候補に**（ユーザー設定で警告許容度を調整可能）。

---

## 4. 日本株固有の補正

### 4.1 株主優待利回り
- データソース: 手動 CSV（`data/yutai/yutai_db.csv`）
  - フィールド: `ticker`, `yutai_value_jpy`, `min_shares`, `holding_period_required`, `last_verified`
- 計算: `yutai_yield = yutai_value_jpy / (min_shares × current_price_jpy)`
- 注意: 過去 5 年で日本企業の優待廃止が増加 → `last_verified` から 6 ヶ月以上経過は ⚠️ 表示

### 4.2 NISA 優先表示
- 現在の枠（年間 360 万 / 累積 1800 万）残量を `data/holdings/portfolio.csv` の account_type から計算
- NISA 推奨銘柄 = 配当 yield 高 + 長期保有スコア高 + 含み益課税ゼロ恩恵大

### 4.3 配当二重課税控除（米国 ADR）
- 米国株の配当は現地 10% + 日本 20.315% の二重課税
- 確定申告で外国税額控除を取得可能（実効税率 ~30%）
- → 米国配当株の真の利回り = forward yield × 0.70（控除後）
- 日本株配当の実効利回り = forward yield × 0.79685（特定）/ 1.00（NISA）

→ **税引後利回りで横並び比較**できるよう Income Score 内で正規化。

---

## 5. データソース統合

| ソース | 取得項目 | キャッシュ TTL |
|---|---|---|
| **EODHD ファンダ** | 配当、Buyback、ROE/ROA、売上、EBITDA、負債、PEG、β | 7d ✅ |
| **EODHD 価格** | OHLCV、出来高、52w high/low | 24h ✅ |
| **SEC EDGAR 13F** | 機関投資家保有 | 90d |
| **SEC EDGAR Form 4** | インサイダー取引 | 24h |
| **FRED** | 金利、Fed BS、雇用統計 | 24h |
| **手動 CSV** | 優待データ | 30d（手動更新） |
| **Tavily** | ガバナンス・規制ニュース | 1h ✅ |
| **Exa** | 学術・ESG レポート | 1h ✅ |

---

## 6. アーキテクチャ

### 6.1 新設モジュール

```
src/analysis/
├── magic_formula.py       (既存)
├── regime.py              (既存)
├── investor_lenses.py     (既存)
├── sentiment.py           (既存)
└── composite_score.py     (NEW: Phase 3.1)
    ├── QualitySubScore
    ├── ValueSubScore
    ├── IncomeSubScore     ← 配当 + Buyback + 優待
    ├── GrowthSubScore
    ├── MomentumSubScore
    ├── RiskSubScore
    ├── ConvictionSubScore
    ├── SentimentSubScore
    ├── CompositeScore     ← サブスコア統合
    ├── INVESTOR_PRESETS   ← Buffett型 / Lynch型 / 配当型 等
    └── compute_composite_score(ticker_df, preset)
```

### 6.2 既存 skill との連携

- `magic-formula-screener` skill → ROC/EY をサブスコア V に投入
- `13f-cloning-tracker` skill → C (Conviction) サブスコアに投入
- `kelly-position-sizer` skill → Composite Score を信頼度として fraction 動的調整
- `regime-detection` skill → Crisis 時はリスクサブスコアの重みを上げる
- `polymarket-macro-watcher` skill → マクロ警告を Risk サブスコアに投入
- `monte-carlo-projection` skill → Composite Score 上位銘柄でポートフォリオ MC 投影

---

## 7. 実装段階（Phase 3）

### Phase 3.1（最優先、本セッション内 TDD 実装）

**配当再投資（Buffett-Coke）+ 破綻リスク（Burry）+ 成長補正（Lynch）+ 自社株買い（Buffett-Munger）**

| 軸 | 関数 | 入力 |
|---|---|---|
| Forward dividend yield | `calculate_forward_dividend_yield(annual_dividend, price)` | EODHD `Highlights.ForwardAnnualDividendYield` |
| 配当成長率 5y CAGR | `calculate_dividend_growth_5y(history)` | 過去 5 年配当履歴 |
| 配当性向 | `calculate_payout_ratio(dps, eps)` | EODHD `Highlights.PayoutRatio` |
| 連続増配年数 | `calculate_consecutive_dividend_years(history)` | 過去配当履歴 |
| Buyback yield | `calculate_buyback_yield(buybacks_4q, market_cap)` | Income statement の "common stock repurchase" |
| Altman Z-Score | `calculate_altman_z(working_capital, retained_earnings, ebit, market_cap, total_liabilities, sales, total_assets)` | Balance sheet + Income statement |
| PEG ratio | `calculate_peg(pe_ratio, earnings_growth_rate)` | EODHD `Highlights.PEGRatio` |
| **Composite Score（4 プリセット）** | `compute_composite_score(rows, preset="buffett")` | EODHD ファンダ集計 |
| **警告システム（4 警告）** | `evaluate_warnings(row)` | dict 集合 |

→ 1 commit で TDD + 実装 + screener UI 統合まで。

### Phase 3.2（次セッション）

- ROIC vs WACC（自前 WACC 計算 = β + risk-free + ERP）
- 優待 CSV 連携 + 6 ヶ月 stale 警告
- NISA 残量管理
- 配当二重課税控除 + 税引後利回り正規化

### Phase 3.3（後続）

- AQR QMJ ファクター
- Carhart 4-factor exposure
- 流動性・スプレッド指標
- ガバナンス（SEC アクション）

---

## 8. UI 統合方針

### 8.1 screener page の刷新
- 「投資スタイル」プリセット選択（ラジオボタン: Buffett / Lynch / 配当 / 逆張り / クローニング / テール回避）
- 結果テーブルに **Composite Score**（0-100）+ **サブスコア 8 軸**（小バッジ）+ **警告アイコン**
- 警告ありは行ハイライト + ⚠️ アイコン
- 既存 Magic Formula スコアは「Greenblatt 軸」として残す

### 8.2 推奨根拠カードの拡張
- ヘッダー: Composite Score + 投資スタイル名
- メイン: 「なぜ推すか」のニュース要約（既存）
- サブスコア レーダーチャート（plotly）で 8 軸を可視化
- 警告アイコン → expander で詳細

### 8.3 home page の刷新（Phase 3.2）
- 保有銘柄ごとに Composite Score を表示
- ポートフォリオ全体の加重 Composite Score
- 規律違反（warning ありの保有）を強調

---

## 9. テスト戦略

### Phase 3.1 必須テスト
- 各サブスコア計算の境界値（Decimal、ゼロ除算ガード、NaN 取扱）
- プリセット重み付けの合算検証（重みの合計 = 100）
- Composite Score の単調性（Q ↑ → Score ↑、ただし他軸固定）
- 警告閾値の境界（Altman Z = 1.8 で警告境界）
- 投資スタイル別プリセットで上位銘柄が変わることの検証

### 統合テスト
- EODHD ファンダレスポンスを fixture 化 → 5 銘柄分の Composite Score 計算
- 投資スタイル変更で順位が変わる E2E

---

## 10. 学術根拠

- Greenblatt 2010, *The Little Book That Still Beats the Market* — ROC + EY
- Altman 1968, *"Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy"* — Z-Score
- Beneish 1999, *"The Detection of Earnings Manipulation"* — M-Score
- Lynch 1989, *One Up On Wall Street* — PEG
- Buffett, Berkshire Annual Letters — ROIC > WACC、Buyback yield、配当再投資
- Asness, Frazzini, Pedersen 2019, *"Quality Minus Junk"* — QMJ
- Carhart 1997, *"On Persistence in Mutual Fund Performance"* — 4-factor model
- Tetlock 2007（既存 SentimentAnalyzer）

---

## 11. 認知バイアス対策（CLAUDE.md §9.7 拡張）

| バイアス | 対策（既存） | 対策（追加） |
|---|---|---|
| Loss Aversion | ATR ストップ ✅ | 警告銘柄の保有を強調 |
| Confirmation Bias | 反対意見併記 ✅ | bull case と bear case を 2 列表示 |
| Recency Bias | 5y ヒストリカル必須 ✅ | 直近 1m / 12m / 5y / 10y 並列表示 |
| Overconfidence | Half-Kelly ✅ | Composite Score < 50 銘柄は強制 fraction 半減 |
| Home Bias | — | 米国/日本/その他の比率表示、過集中時 ⚠️ |
| Anchoring | — | 取得平均ではなく内在価値（DCF）を併記 |

---

## 12. 残課題（オープン）

- DCF（Discounted Cash Flow）モデルの実装範囲
- リアル ESG スコアの取得元（Refinitiv/MSCI は有料、代替ソース調査必要）
- インサイダー取引のリアルタイム性（Form 4 は 2 営業日ラグ）
- 優待データの自動取得（みんかぶ・優待 DB のスクレイピング規約）

→ 設計レビュー時に kabu-analyst agent + planner agent で議論。

---

**この設計を Phase 3.1 から段階実装する。本ドキュメントは生きた設計図として、実装進捗に合わせて更新する。**
