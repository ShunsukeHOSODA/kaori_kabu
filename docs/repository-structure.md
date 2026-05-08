# リポジトリ構造 — kaori_kabu

## トップレベル

```
kaori_kabu/
├── CLAUDE.md / AGENTS.md / README.md       ← Claude / 人間の context
├── pyproject.toml                           ← Python 依存定義 + ツール設定
├── .python-version                          ← uv / pyenv 用 (3.11)
├── .env.example / .env (gitignore)          ← 環境変数
├── .gitignore                               ← Python + 個人投資データ除外
├── .editorconfig                            ← エディタ統一
├── docs/                                    ← 永続的ドキュメント
├── .steering/                               ← 作業単位ドキュメント
├── .claude/                                 ← プロジェクト固有 Claude 設定
├── .github/                                 ← GitHub 統合（CI、テンプレ）
├── .vscode/                                 ← VS Code workspace
├── src/                                     ← アプリコード（パッケージ）
├── tests/                                   ← pytest テスト
├── notebooks/                               ← Jupyter 探索用
├── data/                                    ← データ（gitignore）
├── scripts/                                 ← セットアップ・運用
└── reports/                                 ← QuantStats HTML 出力（gitignore）
```

## src/ の構造（feature-based + layered）

```
src/
├── __init__.py
├── cli.py                                   ← `kabu` コマンドエントリーポイント
│
├── config/                                  ← 設定読み込み（pydantic-settings）
│   ├── __init__.py
│   └── settings.py                          ← .env からロード、型検証
│
├── data/                                    ← Data Layer (外部 API → DataFrame)
│   ├── __init__.py
│   ├── cache.py                             ← parquet キャッシュ層
│   ├── openbb_client.py                     ← OpenBB SDK ラッパー（中核）
│   ├── eodhd.py                             ← EODHD クライアント
│   ├── jquants.py                           ← J-Quants クライアント（日本株正本）
│   ├── sec_edgar.py                         ← SEC EDGAR (13F, Form 4, 10-K)
│   ├── fred.py                              ← FRED マクロ
│   ├── polymarket.py                        ← Polymarket Gamma API
│   ├── openinsider.py                       ← OpenInsider スクレイピング
│   ├── jpx_estat.py                         ← e-Stat / 日銀時系列
│   └── universe.py                          ← financedatabase ラッパー
│
├── analysis/                                ← Analysis Layer (戦略コア)
│   ├── __init__.py
│   ├── magic_formula.py                     ← ROC + Earnings Yield
│   ├── thirteen_f.py                        ← 13F 解析・差分
│   ├── kelly.py                             ← Half-Kelly ポジションサイザー
│   ├── monte_carlo.py                       ← GBM 1000 パスシミュレーション
│   ├── regime_hmm.py                        ← HMM Bull/Choppy/Crisis
│   ├── risk_metrics.py                      ← Sharpe/Sortino/VaR/CVaR
│   ├── atr_stop.py                          ← ATR トレーリングストップ
│   ├── factor_models.py                     ← Fama-French (Phase 2)
│   └── technical.py                         ← pandas-ta ラッパー
│
├── strategies/                              ← Strategy Layer (バックテスト用戦略)
│   ├── __init__.py
│   ├── base.py                              ← Strategy 抽象基底クラス
│   ├── value_screener.py                    ← Magic Formula 戦略
│   ├── clone_13f.py                         ← 13F Cloning 戦略
│   ├── dividend.py                          ← 配当戦略（Phase 2）
│   ├── momentum.py                          ← モメンタム戦略（Phase 2）
│   └── backtest_engine.py                   ← vectorbt ラッパー
│
├── portfolio/                               ← Portfolio Layer (保有銘柄管理)
│   ├── __init__.py
│   ├── holdings.py                          ← portfolio.csv I/O
│   ├── decision_log.py                      ← 売買判断ログ append-only
│   ├── optimizer.py                         ← Riskfolio-Lib ラッパー
│   ├── tax.py                               ← NISA / 特定口座 after-tax 計算
│   └── rebalance.py                         ← リバランスロジック
│
├── dashboard/                               ← Streamlit UI レイヤー
│   ├── __init__.py
│   ├── app.py                               ← エントリーポイント
│   ├── pages/                               ← マルチページ
│   │   ├── 01_home.py                       ← ホーム（保有銘柄 + リスク信号灯）
│   │   ├── 02_screener.py                   ← Magic Formula スクリーナー
│   │   ├── 03_thirteen_f.py                 ← 13F 追従
│   │   ├── 04_backtest.py                   ← バックテスト
│   │   ├── 05_monte_carlo.py                ← Monte Carlo 確率分布
│   │   ├── 06_macro.py                      ← Polymarket / FRED
│   │   └── 07_settings.py                   ← 設定
│   └── state.py                             ← Streamlit セッション状態管理
│
└── ui/                                      ← UI 共通コンポーネント
    ├── __init__.py
    ├── components.py                        ← 信号灯、メトリクスカード等
    ├── charts.py                            ← Plotly チャート関数
    ├── education.py                         ← 3 段階展開の教育レイヤー
    └── theme.py                             ← Streamlit テーマ
```

## tests/ の構造

```
tests/
├── __init__.py
├── conftest.py                              ← 共通フィクスチャ
├── fixtures/                                ← テスト用 parquet / JSON データ
│   ├── eodhd_aapl_2020_2024.parquet
│   ├── sec_13f_brk_2024q3.json
│   └── magic_formula_universe.parquet
│
├── unit/                                    ← ユニットテスト（高速、外部 API モック）
│   ├── analysis/
│   │   ├── test_magic_formula.py
│   │   ├── test_kelly.py
│   │   ├── test_monte_carlo.py
│   │   └── test_risk_metrics.py
│   ├── data/
│   │   ├── test_cache.py
│   │   └── test_eodhd.py (mock)
│   └── portfolio/
│       ├── test_holdings.py
│       └── test_decision_log.py
│
└── integration/                             ← 統合テスト（実 API、@pytest.mark.slow）
    ├── test_openbb_eodhd.py
    ├── test_sec_edgar_13f.py
    └── test_full_pipeline.py
```

## ファイル配置ルール

| カテゴリ | 配置 |
|---|---|
| 戦略実装 | `src/analysis/`（ロジック） + `src/strategies/`（バックテスト連携） |
| 外部 API | `src/data/{provider}.py` |
| ダッシュボードページ | `src/dashboard/pages/{nn}_{name}.py`（番号で順序固定） |
| 共通 UI | `src/ui/` |
| 設定 | `src/config/settings.py` 一箇所に集約 |
| テストフィクスチャ | `tests/fixtures/`（parquet 推奨） |
| テスト | `tests/unit/` または `tests/integration/`（対象モジュール構造をミラー） |
| 探索用ノートブック | `notebooks/`（`.ipynb` または `.py` jupytext） |
| バッチスクリプト | `scripts/`（日次データ取得 cron 等） |

## 命名規則

詳細: [`glossary.md`](./glossary.md) と [`development-guidelines.md`](./development-guidelines.md)

- **ファイル**: `snake_case.py`（Python 標準）
- **モジュール / パッケージ**: `snake_case/`
- **クラス**: `PascalCase`
- **関数 / 変数**: `snake_case`
- **定数**: `UPPER_SNAKE_CASE`
- **型エイリアス**: `PascalCase`
- **import 順**: stdlib → サードパーティ → 自プロジェクト（Ruff isort 自動）

### ティッカー命名

- 米国株: `AAPL`, `MSFT`（サフィックスなし）
- 日本株: `7203.T`, `9432.T`（証券コード + .T）
- ETF: 同様（`SPY`, `1489.T`）

## 禁止パターン

- `utils/` のような曖昧フォルダ → 用途を明確に（`src/data/cache.py`, `src/ui/charts.py` 等）
- 5 階層以上のネスト → flat に再構成
- `from src.data import *` → 明示的 import のみ
- 同一銘柄に複数の DataFrame 形式が混在 → スキーマを `src/data/schemas.py` で統一
- circular dependency → レイヤーを下位層が上位層を知らないように維持

## データディレクトリ（gitignore）

```
data/
├── cache/                          ← API レスポンスキャッシュ
│   ├── eodhd/{ticker}_{date}.parquet
│   ├── jquants/{date}/prices.parquet
│   ├── sec_edgar/{cik}_{quarter}.json
│   ├── fred/{series_id}.parquet
│   └── polymarket/{date}/markets.json
├── holdings/                       ← 保有銘柄（個人データ、絶対 commit 禁止）
│   ├── portfolio.csv
│   └── backups/portfolio_{YYYYMMDD}.csv
├── decision-log/                   ← 売買判断ログ
│   └── {YYYY-MM}.jsonl
├── raw/                            ← 元データダンプ（再処理用）
└── exports/                        ← レポート出力（QuantStats HTML 等）
```

## サブパッケージ（monorepo は不採用）

シングルパッケージ構成を維持。複雑性が増したら検討するが、現状は 1 人開発・1 アプリのため不要。
