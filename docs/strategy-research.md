# 戦略・調査結果 統合ドキュメント — kaori_kabu

> **目的**: 2026-05-09 のセットアップ時に並列 4 エージェントで実施した調査結果と、それに基づく戦略選定の根拠を 1 ファイルに集約する。**「なぜこの構成にしたか」の単一情報源**。

---

## 🎯 プロジェクトのビジョン

**「素人個人投資家が、規律と統計でトップ投資家の運用に近づく」**

### 何を作るか

個人専用ローカルダッシュボード。米日両株式を多角的視点（短期 / 長期 / 配当）で分析し、Magic Formula / 13F Cloning / Monte Carlo / Half-Kelly / HMM レジーム / ATR ストップ の 7 機能で意思決定を支援する。

### なぜ作るか

機関投資家が持つ 3 つの優位性（情報優位性 / 執行速度 / レバレッジ）を個人は永遠に持てない。だから別の土俵で戦う：

| 個人投資家が勝てる土俵 | なぜ勝てる |
|---|---|
| **規律** | Magic Formula を 5 年放置できる人は機関より少ない |
| **長期視点** | 四半期決算プレッシャーがない |
| **統計** | 13F + ファクターで「勝てるベットだけ」に絞れる |
| **小規模性** | 流動性の薄い小型バリューに参加できる |

### 何を作らないか（スコープ外）

- 自動売買（売買は必ず本人判断）
- HFT / スキャルピング（個人で勝てない領域）
- 公開ダッシュボード（金商法対象になるため）
- 暗号資産・オプション・先物（Phase 3 以降検討）

---

## 🔍 並列 4 エージェント調査サマリー（2026-05-09）

### 調査 1: 既存リソース（インストール済み Claude Code 環境）

**結論**: 株運用特化のプラグイン・skill は **存在しない**（ニッチ領域）。汎用ツール 12+ 個を間接的に活用 + **6 独自 skill 新規作成**で 100% カバー。

| カテゴリ | 結果 |
|---|---|
| 直接使える既存ツール | 6 個（dashboard-builder / data-scraper-agent / api-connector-builder / market-research / frontend-patterns / nextjs-turbopack） |
| 間接的に役立つツール | 6 個（pytorch-patterns / continuous-learning / exa-web-search / sequential-thinking / context7 / agent エコシステム） |
| **金融特化ギャップ** | **60%（独自 skill 新規構築で対応）** |

**新規作成した独自 skill（6 個）**:
- `magic-formula-screener` / `monte-carlo-projection` / `13f-cloning-tracker` / `kelly-position-sizer` / `regime-detection` / `polymarket-macro-watcher`

**新規作成した独自 agent**: `kabu-analyst`（データ取得 + 量的分析統合）

---

### 調査 2: OSS 量的分析プラットフォーム

**結論**: 採用したスタックは GitHub スター総計 **11 万超** の業界標準構成。これ以上追加する OSS の限界効用は低い。

#### 🥇 最優先採用（コア 3 つ）

| OSS | スター | 役割 | 採用方針 |
|---|---|---|---|
| **OpenBB Platform** | ~33k | 100+ プロバイダ統合、e-Stat（日本政府統計）2025/9 マージ | データバックボーン |
| **vectorbt** | ~7.3k | Numba ベクトル化で backtrader の 20 倍速 | バックテスト + 確率分布の主役 |
| **Streamlit + Plotly** | ~35k+~17k | Python 完結、学習コスト Next.js の 1/5 | UI 層 |

#### 🥈 補完ライブラリ

| OSS | スター | 役割 |
|---|---|---|
| Riskfolio-Lib | ~3k | Mean-CVaR / HRP / Black-Litterman 全部入り |
| PyPortfolioOpt | ~4.5k | 効率的フロンティア / 入門用 |
| QuantStats | ~5.4k | `qs.reports.html()` で完全 tearsheet |
| pandas-ta | ~5.5k | 150+ テクニカル指標 |
| FinanceDatabase | ~3k | 30 万銘柄マスタ（日本株 TSE 含む） |
| **FinanceToolkit** | **~1.6k** | **150+ 財務指標一括計算（後で追加）** |
| hmmlearn | ~3.1k | HMM レジーム検出 |
| arch | ~1.3k | GARCH ボラティリティ予測 |

#### ❌ 検討したが見送り

| OSS | スター | 見送り理由 |
|---|---|---|
| FinGPT | ~16k | 日本株対応薄い、Claude API 直接利用が筋良い |
| FinRL（強化学習） | ~10k | 研究用、個人本番には早すぎる |
| QuantConnect Lean | ~10k | C# ベース、Python 完結を崩す |
| Hummingbot | ~9k | 暗号資産用、対象外 |
| Zipline | ~18k | Quantopian 倒産で開発停滞 |
| TA-Lib (C 版) | ~9.5k | pandas-ta で代替、ビルド面倒 |
| backtesting.py | ~5.5k | vectorbt と機能重複、開発鈍化 |

詳細は [`learning-resources.md`](./learning-resources.md) 参照。

---

### 調査 3: データソース・API（月額 5,000 円以内）

**結論**: **EODHD All World ($19.99) + J-Quants Light (1,650 円) = 約 4,500 円**で米日両カバー、これがコスト最適解。

#### Polygon.io vs Tiingo vs EODHD 比較

| 項目 | Polygon Starter | Tiingo Power | **EODHD All World** |
|---|---|---|---|
| 価格 | $29/月 | $30/月 | **$19.99/月（最安）** |
| 米国株 | ◎ | ◎ | ◎ |
| **日本株対応** | **✗** | **✗** | **◎ (.T サフィックス)** |
| グローバル取引所 | 米国のみ | 米国 + 中国 | 60+ 取引所 |
| ヒストリカル | 5 年 | 30+ 年 | **30+ 年** |

→ **日本株対応が決定打**。EODHD 単独で米日両カバーできる唯一の選択肢、しかも最安。

#### J-Quants Light を併用する理由

- EODHD は EOD のみ（日本株は 1 日遅延）
- J-Quants Light = 当日データ + JPX 公式（最も信頼性高い）
- 5 年ヒストリカル + 財務情報・配当・分割込
- 月 1,650 円で日本株分析品質が劇的に上がる

#### 無料で必ず使うソース

| ソース | 用途 |
|---|---|
| SEC EDGAR | 米国 13F・Form 4・10-K |
| FRED | 米マクロ |
| EDINET | 日本の有価証券報告書 |
| e-Stat / 日銀時系列 | 日本マクロ |
| Polymarket Gamma | 予測市場 |
| OpenInsider | 米国インサイダー取引集約 |

詳細は [`cost-budget.md`](./cost-budget.md) 参照。

---

### 調査 4: トップ投資家手法 + 数学的手法

**結論**: AI で完全再現は不可能（情報・執行・レバレッジの劣後）。しかし**規律と統計**で個人投資家平均は確実に超えられる。MVP として **7 機能を実装優先度順に選定**。

#### 🏆 MVP 7 機能（実装優先度順）

| # | 機能 | 学術的バックボーン | 実証 |
|---|---|---|---|
| 1 | **Magic Formula スクリーナー** | Greenblatt 2010 / Montier 2006 | 米国年率 17.2%、日本 +10.8% アウトパフォーム |
| 2 | **13F Cloning ダッシュボード** | Schroeder & Posch 2024 / Pabrai "Dhandho" | 3,643 ファンドのクローンが原ファンドにほぼ追従 |
| 3 | **Monte Carlo 確率分布** | Hull "Options, Futures..." Ch.14 | 一本線予測の禁止、確率分布で考える習慣 |
| 4 | **Half-Kelly ポジションサイザー** | Poundstone "Fortune's Formula" / Thorp | フル Kelly で破滅、Half でも 75% の成長率 |
| 5 | **リスク指標（QuantStats）** | Sharpe / Sortino / Calmar / VaR / CVaR | 業界標準、tearsheet 自動生成 |
| 6 | **HMM レジーム検出** | Rabiner 1989 | Bull / Choppy / Crisis 自動判定 |
| 7 | **ATR トレーリングストップ** | Kaminski & Lo 2014 / TradingView | volatility-adaptive で Max DD を 45-65% 削減 |

#### 📈 Phase 2 拡張（5-7 機能）

- Fama-French 5-factor（**注意: 日本市場では機能不全**、Quality + Value 2-factor で代替）
- Polymarket マクロ統合（Fed 利上げ・選挙・景気後退確率）
- 配当戦略（Dividend Aristocrats + 1489 NF日経高配当 50 ETF）
- Riskfolio-Lib による Mean-CVaR 最適化
- インサイダー取引フィードバック（SEC Form 4）
- 税金考慮（NISA / 特定口座 after-tax リターン）
- バックテストエンジン（vectorbt walk-forward + パラメータ最適化）

#### 📚 必読リソース 5 + 3

**書籍**:
- Joel Greenblatt "The Little Book That Still Beats the Market" — Magic Formula 原典
- Mohnish Pabrai "The Dhandho Investor" — 集中バリュー
- William Poundstone "Fortune's Formula" — Kelly Criterion
- Aswath Damodaran "Investment Valuation" — DCF / 相対評価
- Antti Ilmanen "Expected Returns" — ファクター投資

**論文**:
- Fama & French (2017) "International tests of a five-factor asset pricing model" — 日本市場の特殊性
- Schroeder & Posch (2024) "Outperforming the Market: 13F Cloning"
- Kaminski & Lo (2014) — Stop-loss 理論

#### ⚠️ AI で勝てない部分（正直に書く）

- **情報優位性**: HFT・機関は millisecond で板情報・オーダーフロー・代替データ（衛星画像 / クレカ統計）を持つ。個人は永遠に勝てない
- **執行速度**: マーケットメイカーの API レイテンシは μs 単位。スリッページで負ける
- **レバレッジ**: プライムブローカー経由で 10-30 倍。個人は信用 3.3 倍が上限

→ **個人投資家が勝てる土俵**: 規律 / 長期視点 / 統計 / 小規模性

---

## 📊 「素人 → 世界トップクラスに近づく」現実的な道筋

### Step 1: 規律のインストール（Phase 1 MVP）

| 規律 | 実装メカニズム |
|---|---|
| 損切り規律 | ATR トレーリングストップを全保有に強制適用 |
| ポジション制限 | Half-Kelly + 1 銘柄上限 5% + 現金準備 10% |
| バリュー基準 | Magic Formula スコア下位は買わない |
| マーケット環境意識 | HMM Crisis シグナル時に新規買い停止 |

### Step 2: 情報優位性の代替（Phase 2 一部）

| 代替手法 | 実装 |
|---|---|
| トップ投資家追従 | 13F Cloning（45 日遅延だが Buffett / Pabrai のポジションを借りる） |
| マクロ予測 | Polymarket（市場参加者の織り込み確率を取得） |
| インサイダー | SEC Form 4 で役員売買のクラスター検出 |

### Step 3: 統計的優位性の確保（Phase 2 全機能）

| 統計手法 | 期待効果 |
|---|---|
| Fama-French 帰因分析 | 自分のリターンが「ファクター」か「真のアルファ」かを切り分け |
| Monte Carlo シミュレーション | リスク許容度を定量的に測る |
| QuantStats tearsheet | 月次で運用品質を客観評価 |
| 相関行列・HRP | 分散投資の科学的最適化 |

---

## 🧠 認知バイアス対策（仕組みで防ぐ）

| バイアス | 仕組みで対策 |
|---|---|
| **Loss Aversion**（損失回避） | ATR ストップ強制、UI 赤信号、Decision Log 記録 |
| **Confirmation Bias**（確証バイアス） | UI に必ず反対意見・Value Trap 警告を併記 |
| **Recency Bias**（直近バイアス） | 5 年以上のヒストリカル必須、HMM で過去レジーム比較 |
| **Overconfidence**（自信過剰） | Half-Kelly でレバレッジ抑制、Monte Carlo で確率分布提示 |
| **Anchoring**（アンカリング） | UI で取得価格を見ずに判断できるレイアウト |
| **Disposition Effect**（保有株を売れない） | Decision Log で振り返り、月次レビュー |

参考: Daniel Kahneman "Thinking, Fast and Slow"

---

## 🎓 投資判断の 3 段階教育レイヤー（UI 全体方針）

各シグナル・銘柄カードで必ず以下を展開可能にする：

```
┌─ Magic Formula スコア: 87/100 ─────────────┐
│  📊 ROC: 28% (上位 5%)                      │
│  💰 Earnings Yield: 12% (上位 15%)          │
│                                             │
│  🤔 なぜ買い候補?  [▼展開]                   │
│   ├─ ROC が高い = 資本効率の良い会社         │
│   ├─ EY が高い = 利益の割に株価が安い        │
│   └─ Greenblatt 2010 のバックテスト: 年率17% │
│                                             │
│  ⚠️ リスク [▼展開]                           │
│   ├─ Value Trap (構造不況業種かもしれない)   │
│   └─ 直近 3 年は MFD アンダーパフォーム      │
│                                             │
│  📚 もっと学ぶ → "The Little Book..."       │
└─────────────────────────────────────────────┘
```

**目的**: シグナルだけでなく**なぜそう判断するか**と**何が間違っているかもしれないか**を必ず併記。「規律と統計でトップに近づく」ためには、ブラックボックス AI ではなく**理解できる根拠**が必須。

---

## 🛡️ 守るべき投資原則（CLAUDE.md §9 抜粋）

1. **金額は必ず Decimal 型** — float の丸め誤差を避ける
2. **データキャッシュ必須** — API 直接コール禁止、`src/data/cache.py` 経由
3. **一本線の価格予測は禁止** — 必ず確率分布（Monte Carlo fan chart）
4. **シグナルには学術的根拠を必ず併記** — Greenblatt / Fama-French 等の引用
5. **リスク警告を必ず併記** — Value Trap / アンダーパフォーム期間
6. **損切り規律** — ATR ストップを全ポジションに強制適用
7. **税務考慮** — NISA / 特定口座を分離、after-tax リターン
8. **売買履歴は append-only** — 過去データ書き換え禁止

---

## 🔗 関連ドキュメント

| トピック | ファイル |
|---|---|
| 何を作るか（PRD） | [`product-requirements.md`](./product-requirements.md) |
| どう作るか（技術選定） | [`architecture.md`](./architecture.md) |
| どこに何を置くか | [`repository-structure.md`](./repository-structure.md) |
| 月額予算 | [`cost-budget.md`](./cost-budget.md) |
| 学習リソース集 | [`learning-resources.md`](./learning-resources.md) |
| 各戦略の実装詳細 | `.claude/skills/{name}/SKILL.md`（6 個） |
| データ + 分析エージェント | `.claude/agents/kabu-analyst.md` |

---

## 📅 更新履歴

| 日付 | 変更内容 |
|---|---|
| 2026-05-09 | 初版作成（4 並列エージェント調査結果統合） |
| - | （Phase 2 完了後に再評価予定） |

---

## 🔄 このドキュメントの位置づけ

- **永続ドキュメント**（`docs/` 配下）として運用
- 戦略の根拠を変更する場合は ADR を作成（[`docs/ADR/`](./ADR/)）
- 月 1 回見直し（毎月初）、新しい知見を追加
- アンチパターン: 個別の戦略変更は ADR で、全体方針変更はこのファイル
