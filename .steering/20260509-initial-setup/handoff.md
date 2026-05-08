# 引き継ぎプロンプト — 2026-05-09 初期セットアップ完了 → 次セッション

> **使い方**: kaori_kabu ディレクトリに移動して `claude` を起動した後、
> このファイルの「📋 コピペ用プロンプト」セクションを最初のメッセージとして送る。

---

## 📋 コピペ用プロンプト

```
前回セッション（2026-05-09）で以下を完了済みです。これを踏まえて作業継続してください。

## ✅ 完了済み

### プロジェクト立ち上げ
- claude-code-project-v2 テンプレートから kaori_kabu プロジェクトを生成
- CLAUDE.md / README.md / AGENTS.md を株運用固有に書き換え
- docs/{product-requirements, architecture, repository-structure, cost-budget, learning-resources}.md 作成
- src/{config,data,analysis,strategies,portfolio,dashboard,ui}/ 階層作成（__init__.py のみ、実装は未着手）
- Streamlit ダッシュボード app.py + pages/01_home.py 〜 07_settings.py のスケルトン
  （pages/05_monte_carlo.py のみ GBM 1000 パスで動作版を実装済み）
- src/cli.py で `kabu` CLI コマンド (status / dashboard) 実装

### 独自 skill / agent
- .claude/agents/kabu-analyst.md（データ取得 + 量的分析統合エージェント）
- .claude/skills/{magic-formula-screener, monte-carlo-projection, 13f-cloning-tracker,
  kelly-position-sizer, regime-detection, polymarket-macro-watcher}/SKILL.md（6 独自 skill）

### 環境構築（実環境で動作確認済み）
- uv 0.11.11 インストール済み（~/.local/bin/uv）
- Python 3.12.x（uv が自動取得）
- .venv 作成済み、uv sync --extra dev 完了
- 全 23 主要パッケージ import OK（OpenBB SDK + 30 拡張自動検知）
- Streamlit /_stcore/health で `ok` 応答確認済み

### 採用ライブラリ（pyproject.toml）
- データ統合: openbb 4.4+ / eodhd / fredapi / yfinance / jquants-api-client /
  pandas-datareader / financetoolkit / sec-edgar-downloader
- バックテスト: vectorbt 1.0 / backtrader
- ポートフォリオ最適化: riskfolio-lib / PyPortfolioOpt
- パフォーマンス分析: quantstats / empyrical-reloaded
- テクニカル指標: pandas-ta
- 統計・ML: hmmlearn / arch / statsmodels / scikit-learn
- ダッシュボード: streamlit / plotly / altair / matplotlib / seaborn
- 銘柄マスタ: financedatabase 2.3.1
- HTTP / 設定: httpx / tenacity 8.x / pydantic-settings / loguru / rich / click
- データ: pyarrow / duckdb / polars

## 🎯 次にやりたいこと

Magic Formula スクリーナー実装に進む。

### 実装順序（推奨）

1. データレイヤー実装（90 分）
   - src/data/cache.py — parquet キャッシュ層
   - src/data/openbb_client.py — OpenBB SDK ラッパー
   - src/data/eodhd.py — EODHD クライアント

2. Magic Formula 実装（120 分）
   - src/analysis/magic_formula.py — ROC + Earnings Yield 計算
   - tests/unit/analysis/test_magic_formula.py — TDD 先行

3. スクリーナーページ完成（30 分）
   - src/dashboard/pages/02_screener.py の「未実装」プレースホルダを実装
   - 実際の銘柄リスト + Magic Formula スコア表示

合計 約 4 時間で「実際に銘柄が出てくる」状態に到達。

## 🚀 起動コマンド

cd ~/Desktop/kaori_kabu
export PATH="$HOME/.local/bin:$PATH"
uv run streamlit run src/dashboard/app.py

## 🔑 API キー設定状況

未確認。`.env` に以下を入力する必要があり：
- EODHD_API_KEY（必須、$19.99/月）
- JQUANTS_REFRESH_TOKEN（必須、1,650 円/月）
- SEC_EDGAR_USER_AGENT（必須、メアド明記）
- FRED_API_KEY（必須、無料）

## 📝 ハンドオフ詳細

詳細は .steering/20260509-initial-setup/handoff.md を参照。
git log で過去 2 コミットの差分確認可能：
- f74f1af fix(deps): Python 3.12 対応 + 依存パッケージの実在版に修正
- 8610a0d feat: kaori_kabu 初期セットアップ

## 🧠 規約リマインド（CLAUDE.md より）

- 金額は必ず Decimal 型（float 禁止、丸め誤差回避）
- 日付は datetime.date / pd.Timestamp（文字列禁止）
- 通貨は明示（USD / JPY のカラムを必ず持つ）
- API 呼び出しは必ず src/data/cache.py 経由
- 一本線の価格予測は禁止（必ず確率分布で表示）
- シグナルには学術的根拠とリスク警告を必ず併記
- 売買判断は append-only（過去データ書き換え禁止）

まずは現状把握から始めてください。
データレイヤー実装から着手するか、別の優先事項があるか提案してください。
```

---

## 🔧 補足情報（新セッションで Claude が自発的に確認すべき）

### git 状態

```bash
cd ~/Desktop/kaori_kabu
git log --oneline -5
git status
```

### Python 環境確認

```bash
export PATH="$HOME/.local/bin:$PATH"
uv --version          # 0.11.11+
uv run python --version  # 3.12.x
```

### 主要パッケージ動作確認（再検証）

```bash
uv run python -c "import openbb, vectorbt, quantstats, streamlit, financetoolkit; print('OK')"
```

### Streamlit 起動

```bash
uv run streamlit run src/dashboard/app.py
# → http://localhost:8501
# Monte Carlo ページ (pages/05_monte_carlo.py) は API キー不要で動作する実装済み
```

### CLI 動作確認

```bash
uv run kabu status      # API キー設定状況を表示
uv run kabu dashboard   # Streamlit 起動
```

---

## 📂 プロジェクト構造（ざっくり）

```
~/Desktop/kaori_kabu/
├── CLAUDE.md / README.md / AGENTS.md       ← 既読推奨
├── pyproject.toml                          ← 依存定義（修正済み）
├── .env (API キー未設定)
├── .python-version → 3.12
├── .steering/20260509-initial-setup/       ← この handoff を含む
├── docs/                                    ← 仕様書（PRD / Architecture / Cost-Budget 等）
├── src/
│   ├── config/settings.py                  ← 動作確認済み
│   ├── data/                                ← __init__.py のみ、実装待ち ★ 次の主戦場
│   ├── analysis/                            ← __init__.py のみ、実装待ち ★ Magic Formula はここ
│   ├── strategies/                          ← __init__.py のみ
│   ├── portfolio/                           ← __init__.py のみ
│   ├── dashboard/
│   │   ├── app.py                          ← 動作確認済み
│   │   └── pages/
│   │       ├── 01_home.py                  ← プレースホルダ
│   │       ├── 02_screener.py              ← プレースホルダ ★ ここを実装
│   │       ├── 03_thirteen_f.py            ← プレースホルダ
│   │       ├── 04_backtest.py              ← プレースホルダ
│   │       ├── 05_monte_carlo.py           ← 動作版実装済み ✅
│   │       ├── 06_macro.py                 ← プレースホルダ
│   │       └── 07_settings.py              ← 動作版実装済み ✅
│   ├── ui/                                  ← __init__.py のみ
│   └── cli.py                               ← 動作確認済み
├── tests/                                   ← __init__.py のみ、TDD 開始可能
└── data/
    ├── cache/                               ← 各プロバイダ別ディレクトリ作成済み
    ├── holdings/                            ← .gitignore で完全除外
    └── decision-log/                        ← .gitignore で完全除外
```

---

## 🛡️ 守るべき制約（リマインド）

### CLAUDE.md §9.1-9.7 から要点

1. **Decimal 型**: 金額は常に Decimal、float 禁止
2. **キャッシュ必須**: API 直接コール禁止、必ず `src/data/cache.py` 経由
3. **確率分布**: 価格予測は一本線禁止、Monte Carlo の fan chart で
4. **学術的根拠**: シグナルには Greenblatt / Fama-French 等の引用必須
5. **リスク警告**: Value Trap / アンダーパフォーム期間を必ず明示
6. **損切り規律**: ATR トレーリングストップを全保有に適用
7. **税務**: NISA / 特定口座を分離

### 並列エージェント運用

- 探索は `Explore` agent で並列起動
- 銘柄分析は `kabu-analyst` agent
- Python 変更後は `python-reviewer` agent 自動起動
- API キー触るコードは `security-reviewer` agent 必須

---

**このファイルは作業完了後アーカイブ可能（`.steering/` の作業単位ドキュメントは履歴）**
