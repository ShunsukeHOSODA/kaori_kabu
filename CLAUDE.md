# CLAUDE.md — kaori_kabu（かおりんの株運用ダッシュボード）

> このファイルはプロジェクトの**憲法**。`docs/` は法律。`.steering/` は判例。三者を混同しない。

## 1. プロジェクト概要

**kaori_kabu** は、かおりん専用の個人ローカル株運用ダッシュボード兼分析ツール。世界トップ投資家の手法（Magic Formula / 13F Cloning / ファクター投資）と統計的リスク管理（Half-Kelly / Monte Carlo / HMM レジーム検出）を AI で再現し、米国株 + 日本株を多角的視点（短期トレード / 長期投資 / 配当）で分析する。**素人でも規律と統計でトップ投資家に近づく**ことを目的とする。

**重要な前提**:
- 完全に**個人専用ローカル**（金融商品取引法の対象外）
- 投資助言サービスではない（自己責任で売買判断）
- AI 予測は確率分布として表示（一本線予測の禁止）

## 2. グローバル委譲（再定義しない）

| 領域 | 委譲先 |
|---|---|
| 応答言語（日本語固定）/ 人物像 / 好み | `~/.claude/CLAUDE.md` + `~/.claude/rules/personal/` |
| 共通コーディング・テスト・セキュリティ・Git | `~/.claude/rules/common/` |
| Python 規約（PEP 8 / type hints / pytest） | `~/.claude/rules/python/` + ECC `python-patterns` |
| エージェント運用・並列実行・モデル選定 | `~/.claude/AGENTS.md` |
| 47 agents / 181 skills / 79 commands の基盤 | `everything-claude-code` (ECC) |
| 規律的ワークフロー（brainstorming, writing-plans, TDD, verification） | `superpowers` |
| シンプル強制・外科的変更・仮定表面化 | `andrej-karpathy-skills` |
| 知識グラフ操作（vault 連携時） | `arscontexta`（HOSODA_2nd_Brain） |

**応答言語は日本語固定**。コード内コメント・README・エラー解説もすべて日本語。

## 3. ドキュメント二層構造

```
docs/  ← 永続的（北極星）
.steering/[YYYYMMDD]-[title]/  ← 作業単位
```

## 4. セッション開始時の自動アクション

1. **構造把握** — `docs/` 埋まり具合、`.steering/` 進行中ステアリング確認
2. **vault からの文脈復元** — `~/Desktop/Obsidian/HOSODA_2nd_Brain/notes/projects/kaori_kabu.md` を確認、直近 3 セッションを読み「前回どこまで / 次に何を」を提示
3. **保有銘柄の状況把握** — `data/holdings/portfolio.csv` を読み込み、当日の評価額・含み益損・リスク指標（Sharpe / Max DD / VaR）を即座に提示
4. **進行中タスク復元** — `.steering/.../tasklist.md` の未完了を提示

## 5. 株運用プロジェクトの中核設計

### コア技術スタック（`docs/architecture.md` 参照）

| レイヤー | 採用技術 | 理由 |
|---|---|---|
| データ取得 | **OpenBB Platform SDK** | 100+ プロバイダ統合、e-Stat 対応 |
| バックテスト | **vectorbt** | Numba ベクトル化で 20 倍速 |
| ポートフォリオ最適化 | **Riskfolio-Lib** + **PyPortfolioOpt** | Mean-CVaR / HRP / Black-Litterman |
| パフォーマンス分析 | **QuantStats** + **Empyrical** | `qs.reports.html()` で完全 tearsheet |
| テクニカル指標 | **pandas-ta** | TA-Lib より導入簡単、150+ 指標 |
| レジーム検出 | **hmmlearn** | Bull / Choppy / Crisis 3 状態 |
| ダッシュボード | **Streamlit + Plotly** | 学習コスト Next.js の 1/5、Python 完結 |
| 銘柄マスタ | **JerBouma/FinanceDatabase** | 30 万銘柄（日本株 TSE 含む） |

### データソース（`docs/cost-budget.md` 参照）

| ソース | 月額 | 用途 |
|---|---|---|
| **EODHD All World** | $19.99 | 米国 + 60+ 取引所 + 日本株 EOD（30+年） |
| **J-Quants Light** | 1,650 円 | 日本株の正本（JPX 公式、当日データ）|
| SEC EDGAR | 無料 | 米国 13F、ファンダメンタル原本、Form 4 |
| FRED | 無料 | 米マクロ |
| EDINET / e-Stat / 日銀 | 無料 | 日本マクロ・有報 |
| Polymarket / Kalshi | 無料 | 予測市場（Fed 利上げ、選挙等） |
| OpenInsider / WhaleWisdom 無料枠 | 無料 | インサイダー / 13F 補完 |

**月額合計: 約 4,500 円**

### MVP 7 機能（`docs/product-requirements.md` 参照）

1. **Magic Formula スクリーナー** (Greenblatt) — ROC + Earnings Yield
2. **13F Cloning ダッシュボード** — Berkshire / Pabrai / Burry / Ackman 追従
3. **Monte Carlo 確率分布チャート** — 1000 パス GBM、5/50/95 パーセンタイル
4. **Half-Kelly ポジションサイザー** — フル Kelly × 0.5、上限 5%/銘柄
5. **リスク指標タブ** — Sharpe / Sortino / Calmar / Max DD / VaR / CVaR
6. **HMM レジーム検出** — Bull / Choppy / Crisis 信号灯
7. **ATR トレーリングストップ** — Loss Aversion バイアス対策

## 6. ドキュメント生成スキルの出力先固定

| スキル | 出力先 |
|---|---|
| `/prp-prd`（PRD 生成） | `docs/product-requirements.md` |
| `/prp-plan`（実装計画） | `.steering/[YYYYMMDD]-[title]/design.md` |
| `/superpowers:writing-plans` | `.steering/[YYYYMMDD]-[title]/design.md` |
| `/superpowers:brainstorming` | `.steering/[YYYYMMDD]-[title]/requirements.md` |

## 7. 1 ファイル毎承認ゲート

生成スキルが複数ファイルを一度に作ろうとしても **1 ファイル毎に生成 → レビュー → 次へ進む**。

## 8. リサーチ・リユース優先（実装前必須）

1. **OpenBB SDK** に該当機能があるか確認（80% カバー想定）
2. **GitHub 検索** — `gh search repos` / `gh search code`
3. **公式ドキュメント** — Context7（`docs-lookup` agent）
4. **PyPI** — battle-tested ライブラリ優先
5. **Exa / Web 検索** — 最後の手段

## 9. 株運用プロジェクト固有規約

### 9.1 数値の扱い
- **金額は常に Decimal 型**（`from decimal import Decimal`）
- **比率は小数（0.05 = 5%）**で内部処理、UI 表示時のみパーセント変換
- **日付は datetime.date / pd.Timestamp**、文字列で持ち回さない
- **通貨は明示**（USD / JPY のカラムを必ず持つ）

### 9.2 データキャッシュ規約
- API 呼び出しは必ず `data/cache/{provider}/{ticker}_{date}.parquet` にキャッシュ
- EOD データは日次 1 回のみ取得
- レート制限を厳守（EODHD: 100,000/日、J-Quants Light: 60/分）
- キャッシュ TTL: EOD = 24h、ファンダ = 7d、13F = 90d

### 9.3 「予測」の表示ルール
- **一本線の価格予測は禁止**
- 必ず**確率分布 / 信頼区間 / シナリオ** で表示
- Monte Carlo は最低 1000 パス、5/50/95 パーセンタイル明示

### 9.4 「シグナル」の表示ルール
- 各シグナルに**根拠を併記**（Magic Formula スコア、ROC、EY 等）
- 学術的バックボーン引用（Greenblatt 2010 / Fama-French 等）
- **リスク警告を併記**（Value Trap / 直近アンダーパフォーム期間 等）

### 9.5 損切り規律
- ATR トレーリングストップを全ポジションに適用
- ポジション開設時に**売却条件を Decision Log に記録**
- Loss Aversion バイアス対策：UI に「赤信号」表示

### 9.6 NISA / 特定口座の税務考慮
- 銘柄ごとに**口座種別タグ**を保持（NISA / 特定口座 / 旧 NISA）
- after-tax リターン計算を**配当**と**売却益**で分離

### 9.7 認知バイアス警告
- **Loss Aversion** → ATR ストップ強制
- **Confirmation Bias** → 反対意見も併記
- **Recency Bias** → 5 年以上のヒストリカル必須
- **Overconfidence** → Half-Kelly でレバレッジ抑制

### 9.8 Provenance（出所追跡）規約 ★ 全レイヤー必須

**目的**: すべての数値・シグナル・判断結果を**出所まで遡及可能**にする。バグ調査・戦略改善・誤った判断の振り返りに必須。Anthropic Claude Financial Services の "ソース追跡" 設計を参考。

#### 9.8.1 DataFrame 出力に必須メタデータカラム

データレイヤー（`src/data/*.py`）が返す全 DataFrame は以下を含む：

| カラム | 型 | 例 |
|---|---|---|
| `source` | str | `"EODHD"` / `"J-Quants"` / `"SEC EDGAR"` |
| `fetched_at` | pd.Timestamp (UTC) | `2026-05-09 10:30:00+00:00` |
| `cache_hit` | bool | `True` / `False` |
| `cache_age_sec` | int \| None | キャッシュヒット時のみ |

#### 9.8.2 シグナル・スコア出力に必須メタデータ

`kabu-analyst` agent や `src/analysis/*.py` が返す JSON は `metadata` キーに以下を含む：

```python
{
    "metadata": {
        "ticker": "AAPL",
        "calculation_method": "magic_formula_v1",      # アルゴリズムバージョン
        "academic_source": "Greenblatt 2010 Ch.5",     # 学術根拠
        "input_data_period": "2020-01-01 to 2025-12-31",
        "input_data_source": "EODHD",                  # 計算入力のデータ源
        "input_cache_hit": True,
        "calculated_at": "2026-05-09T10:35:00+09:00",
        "code_commit": "8610a0d",                       # 計算時の git commit
    },
    "result": { ... }
}
```

#### 9.8.3 Decision Log（売買判断ログ）の Provenance

`data/decision-log/{YYYY-MM}.jsonl` 1 行の必須フィールド：

```json
{
  "timestamp": "2026-05-09T14:30:00+09:00",
  "action": "BUY",
  "ticker": "AAPL",
  "shares": 10,
  "price_jpy": 25000,
  "rationale": "Magic Formula スコア 87/100、ROC 28%",
  "trigger": {
    "skill": "magic-formula-screener",
    "screener_run_at": "2026-05-09T10:35:00+09:00",
    "screener_metadata": { ... §9.8.2 のメタデータ ... }
  },
  "stop_loss_atr_jpy": 22500,
  "code_commit": "8610a0d"
}
```

→ 後で「なぜこの銘柄を買ったか」を**完全に再現可能**にする。

#### 9.8.4 キャッシュファイルの命名と内部構造

`data/cache/{provider}/{ticker}_{YYYYMMDD}.parquet` のメタデータ（pyarrow schema metadata）に：

- `kabu_source` — 取得元 API
- `kabu_fetched_at` — ISO 8601 UTC
- `kabu_endpoint` — 呼び出した API エンドポイント
- `kabu_params_hash` — リクエストパラメータの SHA256（再現性確認用）

#### 9.8.5 UI 表示でも Provenance を必ず開示

Streamlit ダッシュボードのスコア・チャート横に必ず「ⓘ」アイコンで以下を展開可能に：

- データソース・取得日時
- キャッシュヒット状況
- 計算方法・バージョン
- 学術的根拠

→ ブラックボックスを許さない。**すべての数値は説明できる**。

#### 9.8.6 実装支援

- `src/data/cache.py` に `MetadataMixin` を実装し、全データレイヤーで継承
- `src/analysis/_provenance.py` に `wrap_with_provenance(result, **metadata)` ヘルパー
- pytest fixture で provenance フィールドの存在を強制テスト

## 10. コンテキスト管理

- **300-400k トークンで rot 開始** — 50% 超のコンパクションは避け、`/clear` か新セッション
- **巻き戻し優先** — 失敗後の修正より `Esc Esc` で戻って再プロンプト
- **サブエージェントで隔離** — バックテスト結果分析・銘柄スクリーニングは子コンテキストへ

## 11. 安全装置

- **保有銘柄データ（`data/holdings/`）の削除は必ず確認**
- **API キーをコードに埋め込まない**（`.env` のみ）
- **公開 Git リポジトリへの push 禁止**

## 12. 横断的な品質基準

| 領域 | 詳細 |
|---|---|
| テスト | [`docs/testing-strategy.md`](./docs/testing-strategy.md) — pytest, カバレッジ 80%+ |
| 観測 | [`docs/observability.md`](./docs/observability.md) — 構造化ログ |
| パフォーマンス | [`docs/performance.md`](./docs/performance.md) — バックテスト < 30 秒 |
| セキュリティ | [`docs/security.md`](./docs/security.md) — API キー管理 |
| コスト | [`docs/cost-budget.md`](./docs/cost-budget.md) |

## 13. Obsidian vault 連携

- **vault パス**: `~/Desktop/Obsidian/HOSODA_2nd_Brain`
- **プロジェクトダッシュボード**: `vault/notes/projects/kaori_kabu.md`
- **学んだ投資知識**: `vault/notes/` にアトミックノートとして蓄積

## 14. プロジェクト固有エージェント / スキル

`.claude/skills/` 独自スキル: `magic-formula-screener` / `monte-carlo-projection` / `13f-cloning-tracker` / `kelly-position-sizer` / `regime-detection` / `polymarket-macro-watcher`

`.claude/agents/` 独自エージェント: `kabu-analyst`

## 15. 過去のミス記録（追記型）

- （例）YYYY-MM-DD: 〇〇銘柄で △△ の前提を誤解して損切り遅れ。以後 □□ を必ず確認する
