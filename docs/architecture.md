# 技術仕様書 — kaori_kabu

## テクノロジースタック

### データ取得・統合レイヤー

| 項目 | 選定 | ADR | 理由 |
|---|---|---|---|
| データ統合フレームワーク | **OpenBB Platform SDK 4.4+** | [ADR-0001](./ADR/0001-openbb-as-data-backbone.md) | 100+ プロバイダ統合、e-Stat（日本政府統計）2025/9 マージ、Python 完結 |
| 主要株価データ | **EODHD All World** ($19.99/月) | [ADR-0002](./ADR/0002-data-source-selection.md) | 60+ 取引所、米国 + 日本 + 30+ 年ヒストリカル |
| 日本株正本 | **J-Quants Light** (1,650 円/月) | | JPX 公式、当日データ、5 年ヒストリカル |
| 米国 13F・Form 4 | **SEC EDGAR** (無料) | | 公式ソース、User-Agent 必須 |
| マクロデータ | **FRED API** (無料) | | 米連銀、レート緩い |
| 日本マクロ | **e-Stat / 日銀時系列** (無料) | | 公的統計 |
| 予測市場 | **Polymarket Gamma API** (無料) | | 認証不要、60 req/min |
| インサイダー | **OpenInsider** (スクレイピング) | | 米国 Form 4 集約 |

### 分析・量的計算レイヤー

| 項目 | 選定 | ADR | 理由 |
|---|---|---|---|
| バックテスト | **vectorbt 0.26+** | [ADR-0003](./ADR/0003-vectorbt-vs-backtrader.md) | Numba ベクトル化で 20 倍速 |
| ポートフォリオ最適化 | **Riskfolio-Lib 6.0+** | | Mean-CVaR / HRP / Black-Litterman 全部入り |
| ポートフォリオ最適化（補助） | **PyPortfolioOpt 1.5+** | | 効率的フロンティア / 入門用 |
| パフォーマンス指標 | **QuantStats 0.0.62+** | | `qs.reports.html()` で完全 tearsheet |
| パフォーマンス指標（補助） | **Empyrical-reloaded** | | Sharpe / Sortino / VaR の実装基盤 |
| テクニカル指標 | **pandas-ta 0.3+** | | 150+ 指標、TA-Lib より導入簡単 |
| レジーム検出 | **hmmlearn 0.3+** | | HMM Bull / Choppy / Crisis |
| ボラティリティ予測 | **arch 7.0+** | | GARCH ファミリー |
| 統計推定 | **statsmodels 0.14+** | | Fama-French 回帰、時系列分析 |
| 機械学習 | **scikit-learn 1.5+** | | クラスタリング、特徴量エンジニアリング |
| 銘柄マスタ | **financedatabase 2.4+** | | 30 万銘柄（日本株 TSE 含む） |

### ダッシュボード・UI レイヤー

| 項目 | 選定 | ADR | 理由 |
|---|---|---|---|
| フロントエンド | **Streamlit 1.39+** | [ADR-0004](./ADR/0004-streamlit-vs-nextjs.md) | 学習コスト Next.js の 1/5、Python 完結、ローカル単体稼働 |
| 可視化 | **Plotly 5.24+** | | インタラクティブ、Streamlit ネイティブ |
| 可視化（補助） | **Altair / Matplotlib / Seaborn** | | 静的レポート用 |

### データ永続化・キャッシュ

| 項目 | 選定 | 理由 |
|---|---|---|
| キャッシュ形式 | **Apache Parquet** (pyarrow) | カラムナ、圧縮効率、pandas/polars 親和 |
| ローカル分析 DB | **DuckDB** | OLAP 高速、SQL で直接 parquet クエリ |
| 保有銘柄保存 | **CSV** (`data/holdings/portfolio.csv`) | 人間可読、Excel で開ける、Git 履歴で追える |
| 売買判断ログ | **JSON Lines** (`data/decision-log/*.jsonl`) | append-only、改ざん検知 |

### Python 環境・ツール

| カテゴリ | ツール | 理由 |
|---|---|---|
| Python バージョン | 3.11+ | 型ヒント新機能 |
| パッケージ管理 | **uv** (推奨) / pip | 高速、再現性 |
| ビルドバックエンド | **Hatchling** | PEP 517 標準 |
| リンター・フォーマッター | **Ruff 0.6+** | Black + isort + flake8 を統合 |
| 型チェッカー | **mypy 1.11+** + **pyright** | strict mode、補完 |
| テスト | **pytest 8.3+** | デファクト |
| カバレッジ | **pytest-cov** + **coverage** | 80%+ 必須 |
| Property-based test | **hypothesis 6.112+** | 数値計算ロジック検証 |
| Pre-commit | **pre-commit 3.8+** | Ruff / mypy / pyright 自動実行 |
| ノートブック | **JupyterLab 4.2+** + jupytext | 探索用、git 管理可能 |

### 設定・観測性

| カテゴリ | ツール |
|---|---|
| 設定管理 | **pydantic-settings** (.env 読み込み + 検証) |
| ログ | **loguru** (構造化、回転) |
| CLI 出力 | **rich** (テーブル、プログレスバー) |
| HTTP リトライ | **tenacity** |
| レート制限 | **ratelimit** デコレータ |

## 技術的制約と要件

### 制約

- **完全ローカル稼働**: クラウド前提の設計を避ける（外部 DB / Redis 不要）
- **シングルユーザー**: マルチテナント設計しない
- **Python 単一言語**: 開発体験重視、TypeScript フロント避ける
- **macOS 優先**: 開発機が macOS（Linux でも動くが Windows 未検証）
- **Python 3.11+**: 型ヒント機能、新 stdlib（`tomllib` 等）を使うため

### 要件

- バックテスト: 5 年データ × 100 銘柄 < 30 秒（vectorbt の Numba JIT 前提）
- ダッシュボード初期表示: < 5 秒（OpenBB SDK 初期化込み）
- API キャッシュ: 1 リクエスト 1 ファイル（再呼び出しゼロ）
- メモリフットプリント: < 4GB（10 年 × 1000 銘柄でも収まる polars 使用）

詳細: [`performance.md`](./performance.md)

## アーキテクチャ全体像

```
Streamlit Dashboard (src/dashboard/app.py)
    └─ ホーム / スクリーナー / 13F / バックテスト / Monte Carlo / マクロ / 設定
                ↓
Analysis Layer (src/analysis/)
    └─ magic_formula / thirteen_f / kelly / monte_carlo / regime_hmm / risk_metrics / atr_stop
                ↓
Strategy Layer (src/strategies/)
    └─ value_screener / clone_13f / dividend / momentum / backtest_engine
                ↓
Portfolio Layer (src/portfolio/)
    └─ holdings / decision_log / optimizer / tax / rebalance
                ↓
Data Layer (src/data/)
    └─ openbb_client / eodhd / jquants / sec_edgar / fred / polymarket / cache
                ↓
External APIs
    EODHD / J-Quants / SEC EDGAR / FRED / Polymarket / OpenInsider
```

## レイヤー間の依存ルール

- **下位層は上位層を知らない**（Data Layer は Analysis Layer をインポートしない）
- **横断ユーティリティ**: `src/config/`, `src/ui/` は全層から参照可
- **Decimal 型**: 金額は Data Layer から UI Layer まで Decimal で持ち回す
- **DataFrame 型**: 時系列データは pandas.DataFrame、index は必ず `pd.DatetimeIndex`

## デプロイメント戦略

- **環境**: ローカルのみ（dev = prod、ステージング不要）
- **配布**: 個人利用、配布なし
- **更新**: `git pull && uv sync` で完了
- **データバックアップ**: `data/holdings/`, `data/decision-log/` は **iCloud Drive 自動バックアップ** で対応

## アーキテクチャ判断のルール

- 大きな技術選定は **ADR** に記録（[`ADR/`](./ADR/)）
- パフォーマンス・コスト要件は専用 docs に分離
- ロックイン回避を優先（特に有料 API：OpenBB SDK で抽象化）
- **シンプル原則**: クラウド前提・マルチテナント前提の設計を避ける

## 既存システムとの連携

### Obsidian vault（HOSODA_2nd_Brain）

- **連携方式**: ファイルシステム経由（直接読み書き）
- **読み取り**: `vault/notes/projects/kaori_kabu.md` でプロジェクト経緯を参照
- **書き込み**: 学んだ投資知識を `vault/notes/{title}.md` にアトミックノートとして保存（ユーザー承認後のみ）

### Claude Code（このリポジトリ内）

- **連携方式**: `.claude/skills/` + `.claude/agents/` 経由
- **独自スキル**: `kabu-analyst` agent + 6 つの戦略 skill
- **MCP 連携**: グローバル MCP（Tavily, exa, context7）を Polymarket / ニュース調査で活用
