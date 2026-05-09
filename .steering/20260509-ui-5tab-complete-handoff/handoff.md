# 引き継ぎ — UI 5 タブ再設計完了 → Phase 3.2 / 機能拡張へ

> **作成日**: 2026-05-09
> **対象セッション**: 次回作業開始時の最初の参照ドキュメント
> **前セッション最終コミット**: `b89b8aa` (docs sync)
> **GitHub**: https://github.com/ShunsukeHOSODA/kaori_kabu (Private, SSH 認証)

---

## 1. 前セッションで完了した内容

### A. UI 5 タブ再設計（要件 .steering/20260509-ui-5tab-redesign/）

**「現状機能は 1 つも捨てない、ナビ露出だけ削減」** の方針で 8 → 5 タブに集約。

```
📈 ようこそ          サイト使い方 + 免責 + 始め方ガイド
🏠 ホーム            保有株 + 🟢🟡🔴 市場信号灯 + ATR 利確/損切りアラート
🔍 おすすめ銘柄       4 カテゴリ (長期/中期/短期/急騰候補) + 🐋 達人保有バッジ
🧪 銘柄を調べる       ティッカー入力 → 過去検証 (5 年 + 5 リスク指標) / 将来予測 (Monte Carlo Fan Chart)
⚙️ 設定              API・戦略パラメータ・口座種別
```

13F / マクロ / バックテスト / Monte Carlo の **ロジックは 1 行も削っていない**（裏で温存、URL 直接アクセス可）。

### B. 7 つの実装コミット

| コミット | 内容 |
|---|---|
| `6749260` | Step 1: ナビゲーション 5 タブ整理 + 08_research.py プレースホルダ |
| `c3870f1` | Step 2: ホーム強化 (HMM 信号灯 + ATR アラート) + widgets/ 新設 |
| `aefe522` | Step 3: おすすめ銘柄 4 カテゴリ radio + 🐋 達人保有バッジ + モメンタム型プリセット新設 |
| `b3508f7` | Step 4: 銘柄リサーチ統合 (Plotly チャート + 5 リスク指標 + Monte Carlo GBM) |
| `e15f7f5` | **Critical fix**: pages/ → views/ リネームで Streamlit 自動探索を抑止 |
| `ef15a53` | **Critical fix**: EODHD DataFrame の int RangeIndex を date 列で整合（home.py の HMM 検出も同じバグ修正） |
| `b89b8aa` | Step 8: docs sync (CLAUDE.md / cost-budget.md / repository-structure.md / long-term-investment-architecture.md) + .gitignore 整理 |

### C. テスト

- **223 → 251 件 GREEN**（slow 除く、coverage 除外）
- 新規 28 件:
  - `test_regime_signal.py` 7
  - `test_atr_alert.py` 8
  - `test_famous_holdings.py` 13
  - `test_aggregator.py` 既存 1 件をリネーム（4 → 5 プリセット）

### D. 視覚検証（playwright + ユーザー目視）

5 ページすべて確認済み:
- ホーム: **🟢 強気相場 — 積極買い OK** 信号灯稼働
- おすすめ銘柄: 4 カテゴリ radio + Composite テーブルにバッジ injection
- 銘柄を調べる: AAPL 1276 日分取得、両タブ稼働、Monte Carlo Y 軸 550 まで描画
- ようこそ・設定: ナビ 5 項目維持、API 4 つ全緑

### E. データソース構成（Phase 3.1b 確定）

| ソース | 月額 | 役割 |
|---|---|---|
| **EODHD EOD+Intraday Extended** | $29.99 | 米国 + 日本株 EOD + 米国 Intraday、**Fundamentals 不可** |
| **yfinance** | 無料 | ファンダ補完（米国大型株 ◎、規約グレー） |
| **J-Quants Light** | 1,650 円 | 日本株正本（JPX 公式、当日データ） |
| SEC EDGAR / FRED | 無料 | 米国 13F・マクロ |

**月額合計: 約 6,150 円**

---

## 2. 残タスク（優先順位付き）

### 🔴 優先 1: ホーム表示問題の検証（セッション開始時）
- [ ] `01_home.py` の HMM レジーム検出が **本当に🟢 を返したか** 確認
  - 前セッションで「判定中」フォールバックから「🟢 強気相場」に変わった
  - キャッシュ 24h あるので、初回起動時に正常動作か再確認
  - VIX シンボル `VIX.INDX` で取れない場合は別シンボル試行（`VIX.US` 等）
- [ ] ATR アラートが正しい currency（USD/JPY）で表示されるか
  - 米国株（AAPL）: USD 表記
  - 日本株（7203.TO）: JPY 表記
  - holdings/portfolio.csv にサンプル銘柄があれば実際の表示を見る

### 🟠 優先 2: VIX 取得失敗時の代替パス（30 分）
- [ ] `_detect_market_regime_cached` で VIX 取得不可なら、SPY の realized_vol を VIX 代用に
- [ ] regime.py の `prepare_features` の VIX 引数を Optional に拡張（要 test 更新）
- [ ] Phase 3.1b では「判定中」表示でも実用上問題ないが、改善版として実装

### 🟡 優先 3: Phase 3.2 機能（中規模、価値高）
1. **#5 リスク指標タブ独立化** — 保有銘柄全体の Sharpe/Sortino/Calmar/Max DD/VaR/CVaR
   - empyrical-reloaded で 30 分実装可能
   - ホーム or 新タブで保有銘柄に対し計算
2. **#2 13F Cloning 動的化** — `src/data/sec_edgar.py` の XML パーサ実装
   - `famous_holdings.py` の静的辞書を SEC EDGAR から動的取得に置換
   - 13F-HR の四半期更新追従
3. **#7 ATR トレーリングストップ Decision Log 連携**
   - ATR 抵触時に `data/decision-log/{YYYY-MM}.jsonl` に自動記録
   - CLAUDE.md §9.5 規約準拠

### 🟢 優先 4: Phase 3.3（バックテスト深化）
- [ ] vectorbt + QuantStats バックテスト稼働化
- [ ] 04_backtest.py / 05_monte_carlo.py のロジックを `src/dashboard/research/` 配下に関数化
  - `backtest_panel.py` / `monte_carlo_panel.py` として 08_research.py から呼び出せるように
- [ ] 戦略別比較（Buy & Hold / SMA Cross / Mean Reversion）

### 🔵 優先 5: Phase 3.4 / その他
- [ ] FRED + Polymarket + HMM regime 統合（マクロ環境のスコア化）
- [ ] EDINET / e-Stat 日本マクロ実装
- [ ] J-Quants から実際に日本株データ取得テスト（kaori が API トークン入力済 ✅）

---

## 3. セッション開始時に自動でやってほしいこと

```bash
cd /Users/kaori/Desktop/kaori_kabu

# 1. 直近の git 状況把握
git log --oneline -10
git status --short

# 2. テストが緑のままか確認
export PATH="$HOME/.local/bin:$PATH"
uv run pytest --no-cov -m "not slow" -q | tail -3
# 期待値: 251 passed, 3 deselected

# 3. 残タスクの再確認
cat .steering/20260509-ui-5tab-complete-handoff/handoff.md
```

ユーザーへの最初の問いかけ（候補）:
> 「前回 UI 5 タブ再設計が完成 + 視覚検証も OK。残タスクは
> 🔴 ホーム表示再確認 / 🟠 VIX 代替パス / 🟡 Phase 3.2 (リスク指標タブ独立 / 13F 動的化 / Decision Log) / 🟢 Phase 3.3 バックテスト深化。**どれから着手？**」

---

## 4. 動作確認済みコマンド

```bash
# テスト全体（slow 除く）
uv run pytest --no-cov -m "not slow" -q

# 特定ウィジェットテストだけ
uv run pytest --no-cov -m "not slow" -q tests/unit/dashboard/widgets/

# ruff lint
uv run ruff check src/

# 全 .py ファイルの parse check
uv run python -c "
import ast, glob
for f in glob.glob('src/**/*.py', recursive=True):
    ast.parse(open(f).read())
print('all files parse OK')
"

# Streamlit ダッシュボード起動（バックグラウンド）
uv run streamlit run src/dashboard/app.py --server.port 8520 --server.headless true

# 起動状態確認
lsof -iTCP:8520 -sTCP:LISTEN

# 停止
kill $(lsof -tiTCP:8520 -sTCP:LISTEN)
```

---

## 5. 既知の限界・注意

### Chrome 自動翻訳問題（部分的に未解決）
- `<meta name="notranslate">` を `<head>` に注入する方法が Streamlit 標準 API になく、`<body>` 注入では Google 翻訳が無視する
- サイドバーは `st.navigation` の絵文字 + 日本語タイトルで対応済み
- ただし「銘柄を調べる」→「銘柄を網羅」、「暴落」→「一斉」等の誤訳は残る
- 必要に応じて個別 `<span translate="no">` で守る

### Streamlit 自動探索バグ（解決済み、再発防止）
- `pages/` という名前のフォルダは Streamlit が自動探索 **st.navigation を上書き** する仕様
- `views/` にリネームで完全回避済み
- **新ページ追加時は必ず `views/` 配下に配置**、`pages/` という名前のフォルダを作らない

### EODHD DataFrame の index 注意点（解決済み、知識として温存）
- `EODHDClient.get_eod` は date を **列** として返す（`reset_index(drop=True)`）
- `df.index` は int RangeIndex なので `df.index.min().date()` は **TypeError**
- 必ず `pd.to_datetime(df["date"])` 経由で日付として扱う
- 同様に `spy.index.intersection(vix.index)` は位置整数の intersection で日付整合にならない

### VIX シンボル
- `VIX.INDX` で動作確認したが、HMM 学習用に十分なヒストリカルが取れるかは未検証
- 取れない場合は SPY-only 代替パス（優先 2）で対応

### yfinance 制約
- Yahoo Finance の非公式 API、商用 SLA 無し、規約グレー
- 米国大型株は十分、小型・日本株（東証）は欠損あり
- レート制限・突然 API 変更のリスク
- 個人利用限定なので公開 deployment 不可

### EODHD サブスク制約
- 現プラン: **$29.99 EOD+Intraday All World Extended**
- 含む: 全世界 EOD + 米国 Intraday from 2004
- 含まない: **Fundamentals**, ティック, ニュース API
- アップグレード時: ALL-IN-ONE $99.99（年払 $83.33）が最コスパ

### git config 警告
- 各 commit で「Your name and email address were configured automatically」警告が出る
- 抑制したい場合: `git config --global user.email "..."` `git config --global user.name "..."`
- 機能影響なし

---

## 6. 主要ファイルマップ

```
src/dashboard/app.py              — st.navigation エントリ + Welcome ページ (5 タブ)
src/dashboard/views/              — ★ 旧 pages/ をリネーム（自動探索回避）
  01_home.py                      — 保有 + 信号灯 + ATR アラート
  02_screener.py                  — おすすめ銘柄 4 カテゴリ + バッジ
  03_thirteen_f.py                — ナビ非表示、URL 直接アクセス可
  04_backtest.py                  — ナビ非表示、Phase 3.3 で関数化予定
  05_monte_carlo.py               — ナビ非表示、Phase 3.3 で関数化予定
  06_macro.py                     — ナビ非表示、Phase 3.4 で統合予定
  07_settings.py                  — 設定
  08_research.py                  — ★ 銘柄リサーチ統合（過去/将来タブ）

src/dashboard/widgets/            — ★ 新規（テスト容易な分離）
  regime_signal.py                — 🟢🟡🔴 信号灯ロジック + render
  atr_alert.py                    — ATR アラートロジック + render（currency 対応）

src/data/famous_holdings.py       — ★ 新規 達人保有静的辞書（Phase 3.2 で動的化）
src/data/eodhd.py                 — EODHD クライアント (get_eod / get_returns; Fundamentals 403)
src/data/yfinance.py              — yfinance ラッパー（EODHD shape 互換でファンダ供給）

src/analysis/regime.py            — HMM Bull/Choppy/Crisis 検出（既存）
src/analysis/composite/           — 7 軸 Composite Score
  presets.py                      — 5 プリセット (Buffett/配当再投資/Lynch/逆張り/モメンタム ★ 新)
src/strategies/atr_stop.py        — ATR トレーリングストップ計算（既存）

tests/unit/dashboard/widgets/     — ★ 新規（15 ケース）
tests/unit/data/test_famous_holdings.py — ★ 新規（13 ケース）

.steering/20260509-ui-5tab-redesign/  — 要件 + 設計 doc
.steering/20260509-phase-3-1b-handoff/ — 前セッション handoff
.steering/20260509-ui-5tab-complete-handoff/ — このファイル
```

---

## 7. Streamlit 起動状態

- バックグラウンド起動: 前セッション task `bgqiqh774` (port 8520)
- ステータス確認: `lsof -iTCP:8520 -sTCP:LISTEN`
- 停止: `kill $(lsof -tiTCP:8520 -sTCP:LISTEN)`
- 新セッション開始時にプロセスが残ってる場合は `kill` してから `uv run streamlit run...` で再起動推奨

---

## 8. 次セッション最初の操作（推奨）

1. このファイル `.steering/20260509-ui-5tab-complete-handoff/handoff.md` を読む
2. `git status` + `git log --oneline -10` で現状確認
3. テスト緑チェック（`pytest -m "not slow" -q | tail -3` で 251 passed 確認）
4. Streamlit が稼働中か確認、必要なら再起動
5. ユーザーに「優先 🔴 ホーム再確認 / 🟠 VIX 代替パス / 🟡 Phase 3.2 / 🟢 Phase 3.3 — どれから着手？」と聞く

---

## 9. 学んだこと（再発防止メモ）

### Streamlit st.navigation の罠
- **`pages/` という名前のフォルダは Streamlit が自動探索する magic**
- `st.navigation([...])` を呼んでも、同名フォルダがあるとサイドバーに混在する
- 新ページ追加時は `views/`（または他の名前）配下にする鉄則

### EODHD DataFrame の構造
- `date` は **列**、index は int RangeIndex
- 時系列分析では `pd.to_datetime(df["date"])` で datetime に変換してから処理
- `.intersection()` 等で日付整合する場合は必ず datetime index にしてから

### Streamlit `@st.cache_data` の罠
- 引数に `pd.Series` 等を渡すとキャッシュキー計算で TypeError になる
- アンダースコア prefix `_arg` で hash 除外、または `cache_resource` を使う
- 今回は `(api_key, lookback_days)` のシンプル引数で回避

### Chrome 自動翻訳の限界
- Streamlit に `<head>` API が無いため `<meta name="notranslate">` を入れられない
- サイドバーは `st.navigation` のタイトル文字列に絵文字を含めると翻訳率が下がる
- 個別固有名詞は `<span translate="no">英語</span>` で守る
