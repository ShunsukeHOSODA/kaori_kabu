# タスクリスト — 20260509-initial-setup

## ✅ 完了

- [x] claude-code-project-v2 テンプレートから kaori_kabu 生成
- [x] CLAUDE.md / README.md / AGENTS.md を株運用固有に書き換え
- [x] docs/{product-requirements, architecture, repository-structure, cost-budget, learning-resources}.md 作成
- [x] src/ 階層作成 (__init__.py 配置)
- [x] Streamlit ダッシュボード app.py + 7 ページのスケルトン
- [x] pages/05_monte_carlo.py の GBM 動作版実装
- [x] pages/07_settings.py の動作版実装
- [x] src/cli.py 実装 (kabu status / dashboard)
- [x] src/config/settings.py 実装 (pydantic-settings)
- [x] .claude/agents/kabu-analyst.md 作成
- [x] .claude/skills/{6 個}/SKILL.md 作成
- [x] uv インストール + Python 3.12 取得 + .venv 作成
- [x] uv sync --extra dev 成功（全依存解決）
- [x] 23 主要パッケージ import OK 確認
- [x] Streamlit /_stcore/health 動作確認

## ⏳ 次セッション

### Phase 1 MVP（優先度順）

- [ ] **データレイヤー** (推定 90 分)
  - [ ] `src/data/cache.py` — parquet キャッシュ層 + TTL 管理
  - [ ] `src/data/openbb_client.py` — OpenBB SDK ラッパー
  - [ ] `src/data/eodhd.py` — EODHD 直接クライアント
  - [ ] `src/data/jquants.py` — J-Quants 日本株クライアント

- [ ] **Magic Formula 実装** (推定 120 分)
  - [ ] `tests/unit/analysis/test_magic_formula.py` — TDD 先行
  - [ ] `src/analysis/magic_formula.py` — ROC + EY 計算ロジック
  - [ ] `src/dashboard/pages/02_screener.py` — UI 完成
  - [ ] 教育レイヤー（3 段階展開）実装

- [ ] **保有銘柄管理** (推定 60 分)
  - [ ] `tests/unit/portfolio/test_holdings.py` — TDD
  - [ ] `src/portfolio/holdings.py` — portfolio.csv I/O
  - [ ] `src/portfolio/decision_log.py` — append-only ログ
  - [ ] `src/dashboard/pages/01_home.py` — UI 完成

- [ ] **リスク指標** (推定 60 分)
  - [ ] `src/analysis/risk_metrics.py` — QuantStats ラッパー
  - [ ] ホーム画面に Sharpe / Max DD 表示

### Phase 2

- [ ] **13F Cloning** (推定 90 分)
- [ ] **HMM レジーム検出** (推定 60 分)
- [ ] **ATR トレーリングストップ** (推定 45 分)
- [ ] **Half-Kelly ポジションサイザー** (推定 45 分)
- [ ] **バックテストエンジン** (推定 120 分)
- [ ] **Polymarket マクロウォッチャー** (推定 60 分)

## 📌 タスク外（運用）

- [ ] `.env` に API キー入力（EODHD / J-Quants / SEC EDGAR / FRED）
- [ ] Obsidian vault に `notes/projects/kaori_kabu.md` を作成
- [ ] `git remote add` で Private GitHub レポ追加（オプション）
