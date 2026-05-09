# 引き継ぎ — Phase 3.1b 完了 → Phase 3.2 / UI 仕上げ

> **作成日**: 2026-05-09
> **対象セッション**: 次回作業開始時の最初の参照ドキュメント
> **前セッションコミット**: `21d2213` (dashboard 日本語化), `ced056e` (yfinance + EODHD モメンタム)
> **GitHub**: https://github.com/ShunsukeHOSODA/kaori_kabu (Private, SSH 認証)

---

## 1. 前セッションで完了した内容

### A. Phase 3.1b 仕上げ
- ✅ `EODHDClient.get_returns(ticker, *, exchange, as_of)` — 12m / 1m モメンタムリターン
  を `adjusted_close` から Decimal で算出。`get_eod` 経由で 24h キャッシュ共有
  - `_compute_horizon_return` ヘルパー、履歴不足・0 価格除算を安全フォールバック
  - TDD 5 ケース GREEN
- ✅ `src/dashboard/pages/02_screener.py` の `build_composite_inputs_from_fundamentals`
  に `momentum_inputs: MomentumSubScoreInputs | None` を配線
- ✅ `_fetch_momentum_inputs(client, ticker, exchange)` ヘルパーで境界処理
  （httpx/EODHD/ValueError は握って軸 0 点フォールバック）

### B. EODHD Fundamentals 403 問題の解決
- ⚠️ 発見: ユーザーの EODHD サブスク (**$29.99 EOD+Intraday Extended**) は
  Fundamentals API 不可。`/fundamentals/AAPL.US` → 403 Forbidden
- ✅ 対策: `src/data/yfinance.py` 新設、`YFinanceClient.get_fundamentals` を
  EODHD と同じ dict shape で返すよう正規化
  - 既存 `extract_magic_formula_row` / `build_composite_inputs_from_fundamentals`
    が無修正で動く
  - TDD 16 ケース GREEN（ファンダ shape / Magic Formula 互換 / cache /
    シンボル構築 / edge case / build_screener_universe）
- ✅ screener.py で **価格=EODHD / ファンダ=yfinance の固定分業** に変更
- ✅ 月額追加コスト 0 円で Magic Formula スクリーナーが稼働。$59.99 / $99.99
  アップグレード回避

### C. UI 大改修
- ✅ サイドバー日本語化 — `st.navigation` でハイブリッドラベル
  - 📈 ようこそ / 🏠 ホーム / 📊 割安銘柄探し / 🐋 達人追従（13F）
    / 🔬 過去検証 / 🎲 将来予測 / 🌍 マクロ経済 / ⚙️ 設定
  - URL は英語維持（`/home`, `/screener`, `/thirteen-f` 等）→ Chrome 自動翻訳の
    主要発火源を消した
- ✅ Welcome ページに「サイドバーの使い方」一覧表追加
- ✅ 全 7 ページの素人向け用語化
  - `02_screener`: ROC → 資本利益率(ROC)、EY → 益利回り(EY)
  - `03_thirteen_f`: ファンド名を「Berkshire｜バフェット」hybrid 表記
  - `04_backtest`: CAGR/Sharpe/Sortino/Calmar/Max DD 等 11 指標に
    「何の指標？」「良い目安」付き表
  - `05_monte_carlo`: μ/σ/percentile/fan chart の素人向け解説
  - `06_macro`: Polymarket/FRED/HMM (強気/横ばい/暴落) 解説
  - `07_settings`: API ロール説明、戦略パラメータに help ツールチップ
- ✅ Chrome 自動翻訳対策
  - `src/ui/theme.py` に `<meta name="notranslate">` + JS で `html.lang=ja`
  - 英語固有名詞を `<span translate="no">` で保護（FRED → フレッド翻訳化を抑止）

### D. テスト
- ✅ **223 件 PASS**（unit + integration、slow 除く、coverage 除外）
- 新規 21 件: `TestGetReturns` 5 + `Test*Yfinance*` 16

---

## 2. 残タスク（優先順位付き）

### 🔴 優先 1: ドキュメント整合性（5 分）
- [ ] `CLAUDE.md §5 コスト表` を **EODHD $29.99 (Extended、Fundamentals 不可)
      + yfinance ファンダ無料** に更新
- [ ] `docs/cost-budget.md` 同上、yfinance の制約も明記
  （米国大型株 ◎ / 小型・日本株 △、SLA 無し、規約グレー）
- [ ] `docs/long-term-investment-architecture.md` Phase 3.1b 完了マーク

### 🟠 優先 2: UI バグ修正（10 分）
- [ ] `/welcome` URL 直接アクセス時の「ページが見つかりません」ダイアログ
      → `default=True` ページに `url_path="welcome"` 併設可能か検証
- [ ] `01_home.py` の含み損益が Chrome に「含まれる利益」と訳される件
      → `<span translate="no">` 適用 or `unsafe_allow_html=True`
- [ ] `.gitignore` 追加: `.playwright-mcp/`, `*-after.png`, `*-result.png`,
      `*-labels.png`, `*-with-guide.png`
- [ ] `tests/integration/test_composite_e2e.py` に momentum 経路の統合テスト追加
      （Phase 3.1b 引き継ぎ）

### 🟡 優先 3: セキュリティ判断（ユーザー判断必要）
- [ ] **EODHD API トークン再生成の検討** — 前セッションで Playwright snapshot に
      トークンが記録された。`.playwright-mcp/` の YAML に残っている可能性あり。
      プライベートリポなので必須ではないが、安全のため再生成して `.env` を更新
      するのが推奨

### 🟢 優先 4: MVP 7 機能の未実装分（中規模、価値高）
1. **#5 リスク指標タブ** — Sharpe/Sortino/Calmar/Max DD/VaR/CVaR
   - empyrical-reloaded で 30 分実装可能
   - ホーム or 新タブで保有銘柄に対し計算
2. **#7 ATR トレーリングストップ UI** — `src/strategies/test_atr_stop.py` のロジック
   は既存、配線のみ（ホームに警告灯追加 30 分）
3. **#6 HMM レジーム検出** — `hmmlearn` 依存あり、`src/analysis/regime_hmm.py` 新規
   - 06_macro ページの「市場レジーム」タブを稼働化
4. **#2 13F Cloning** — `src/data/sec_edgar.py` の XML パーサ実装
   - 03_thirteen_f ページを稼働化

### 🔵 優先 5: データソース未実装（Phase 3.2 以降）
- J-Quants Light（日本株ファンダ正本、月 1,650 円）
- SEC EDGAR XBRL（米国 10-K 正本、無料）
- FRED（米マクロ）/ Polymarket（予測市場）/ EDINET / e-Stat

### ⚪ 優先 6: Phase 3.2 / 3.3 / 3.4 計画
- **Phase 3.2**: ROIC/WACC + 連続増配年数 + 13F 統合 + 株主優待
- **Phase 3.3**: vectorbt + QuantStats バックテスト稼働化
- **Phase 3.4**: Polymarket + FRED + HMM regime 統合

---

## 3. セッション開始時に自動でやってほしいこと

```bash
# プロジェクトルート
cd /Users/kaori/Desktop/kaori_kabu

# 1. 直近の git 状況把握
git log --oneline -10
git status --short

# 2. テストが緑のままか確認
export PATH="$HOME/.local/bin:$PATH"
uv run pytest --no-cov -m "not slow" -q | tail -3
# 期待値: 223 passed, 3 deselected

# 3. 残タスクの再確認
cat .steering/20260509-phase-3-1b-handoff/handoff.md
```

ユーザーへの最初の問いかけ：
> 「前回 Phase 3.1b 完了 + Welcome 日本語化 + 全ページ素人化 + GitHub Push まで。
>  残タスクは A: docs / B: UI バグ / C: 残 MVP 機能。**A → B → C** の順か
>  どれか先にやる？」

---

## 4. 動作確認済みコマンド

```bash
# テスト全体（slow 除く）
uv run pytest --no-cov -m "not slow" -q

# yfinance 実 API 統合テスト
uv run pytest tests/unit/data/test_yfinance.py::TestYFinanceClientIntegration -m slow -v

# EODHD 実 API テスト（Fundamentals は 403 で fail、EOD のみ pass）
uv run pytest tests/unit/data/test_eodhd.py::TestEODHDClientIntegration -m slow -v

# Streamlit ダッシュボード起動
uv run streamlit run src/dashboard/app.py --server.port 8520

# ruff lint
uv run ruff check src/

# parse check 全体
uv run python -c "
import ast, glob
for f in glob.glob('src/**/*.py', recursive=True):
    ast.parse(open(f).read())
print('all files parse OK')
"
```

---

## 5. 既知の限界・注意

### Chrome 自動翻訳問題（部分的に未解決）
- `<meta name="notranslate">` を `<head>` に注入する方法が Streamlit 標準 API になく、
  `<body>` 注入では Google 翻訳が無視する
- サイドバー & 主要 UI は `<span translate="no">` と日本語化で対応済み
- 残: ページ本文の英語固有名詞のうち span 未適用箇所が翻訳される
  → 必要に応じて随時 span 追加

### yfinance 制約
- Yahoo Finance の非公式 API、商用 SLA 無し
- 米国大型株は十分、小型・日本株（東証）は欠損あり
- レート制限・突然 API 変更のリスク
- 個人利用限定（規約グレー）

### EODHD サブスク制約
- 現プラン: **$29.99 EOD+Intraday All World Extended**
- 含む: 全世界 EOD、米国 Intraday from 2004
- 含まない: **Fundamentals**, ティック, ニュース API
- アップグレード時: ALL-IN-ONE $99.99（年払 $83.33）が最コスパ

---

## 6. 主要ファイルマップ

```
src/data/eodhd.py             — EODHD クライアント (get_eod, get_fundamentals→403, get_returns)
src/data/yfinance.py          — yfinance ファンダラッパー (新規, EODHD shape 互換)
src/data/cache.py             — Parquet TTL キャッシュ
src/data/_provenance.py       — DataFrame.attrs メタデータ

src/analysis/composite/       — 7 軸 Composite Score
  aggregator.py               — compute_composite_score 主関数
  presets.py                  — 4 プリセット (Buffett/配当再投資/Lynch/逆張り)
  subscores/                  — Q/V/I/G/R/M/S 各軸ロジック
  warnings.py                 — Altman/leverage/Falling Knife 等

src/dashboard/app.py          — st.navigation エントリ + Welcome ページ
src/dashboard/pages/          — 各ページ (01_home 〜 07_settings)
src/ui/theme.py               — CSS + 翻訳抑止 meta/JS
src/ui/components.py          — composite_radar_chart 等

tests/unit/data/test_eodhd.py    — 21 ケース (TestGetReturns 含む)
tests/unit/data/test_yfinance.py — 16 ケース (新規)
tests/integration/test_composite_e2e.py — Phase 3.1b マージ前ゲート
```

---

## 7. Streamlit 起動状態

- バックグラウンド起動: 前セッション task `bzjj1c36y` (port 8520)
- ステータス確認: `lsof -iTCP:8520 -sTCP:LISTEN`
- 停止: `kill $(lsof -tiTCP:8520 -sTCP:LISTEN)`

---

## 8. 次セッション最初の操作（推奨）

1. このファイル `.steering/20260509-phase-3-1b-handoff/handoff.md` を読む
2. `git status` + `git log --oneline -5` で現状確認
3. テスト緑チェック
4. ユーザーに「優先 A → B → C どれから着手？」と聞く
