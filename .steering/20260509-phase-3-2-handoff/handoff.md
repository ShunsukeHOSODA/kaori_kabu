# 引き継ぎ — Phase 3.2 リスク指標タブ独立化 完了 → 次は ATR Decision Log / 13F 動的化

> **作成日**: 2026-05-09
> **対象**: 次回作業開始時の最初の参照ドキュメント
> **本セッション最終コミット**: `32e4130`
> **GitHub**: https://github.com/ShunsukeHOSODA/kaori_kabu (Private, SSH 認証)

---

## 1. 本セッションで完了した内容

### A. ATR USD 表示バグ修正 (`d98839c`)

実機検証中に発見:

- Streamlit Markdown レンダラの KaTeX が `$...$` を inline math として解釈
- USD `$` 記号が 2 個連続出現すると「基準 $277、現在 $293」のうち `$277、現在 $` が数式扱いになり、UI 上で「基準 \`277、現在\` 293」と崩れる
- `_CURRENCY_SYMBOLS["USD"]` を `r"\$"` に変更し、Markdown 上でリテラル `$` にエスケープ
- JPY/EUR/GBP は KaTeX delimiter と衝突しないため変更不要
- 回帰テスト 3 件追加（USD/JPY/未知通貨）

### B. Phase 3.2 リスク指標タブ独立化 (`32e4130`)

ホームに「📊 リスク指標」セクションを統合:

- empyrical-reloaded で Sharpe / Sortino / Calmar / Max DD / VaR / CVaR / 年率リターン / 年率ボラの **8 種** を計算
- 評価額ベースのウェイトで 1 年分 EOD（370 日）からポートフォリオリターンを合成
- 評価できなかった銘柄（404 等）はリスク計算から除外（graceful degradation）
- CLAUDE.md §9.8 Provenance 規約完全準拠（calculation_method / academic_source / input_data_period / code_commit / var_confidence）
- ⓘ 計算根拠 (Provenance) expander で出所開示 + Recency/Confirmation Bias 警告併記

新規ファイル:

| ファイル | 役割 |
|---|---|
| `src/analysis/risk_metrics.py` | 純関数（compute_portfolio_returns / compute_risk_metrics）+ RiskMetrics frozen dataclass |
| `src/dashboard/widgets/risk_metrics_panel.py` | 4×2 metric グリッド + Provenance expander。container 注入で Streamlit 非依存テスト容易 |
| `tests/unit/analysis/test_risk_metrics.py` | 12 ケース（純関数 5 + 指標計算 7） |
| `tests/unit/dashboard/widgets/test_risk_metrics_panel.py` | 4 ケース（columns 構造 / Provenance / バイアス警告 / VaR ラベル %） |

修正:

| ファイル | 変更 |
|---|---|
| `src/dashboard/views/01_home.py` | 評価結果テーブル直後・ATR 前に「📊 リスク指標」セクション挿入（70 行） |

### C. テスト

- **251 → 270 件 GREEN**（slow 除く、coverage 除外）
- 新規内訳: ATR USD 3 件 + risk_metrics 12 件 + risk_metrics_panel 4 件 = **19 件**

### D. 実機検証 (Playwright + 目視)

ホーム + サンプル portfolio.csv (AAPL/US + 7203/TO) で:

- 🟢 HMM 信号灯「強気相場 — 積極買い OK」（VIX.INDX 経由）
- AAPL 評価: **439,980 円**、含み益 **+189,980 円 (+75.99%)**
- ATR アラート 🟢 安全圏 1 銘柄、`$277` / `$293` リテラル正しく描画 ✅
- リスク指標 8 種:
  - Sharpe **1.78** / Sortino **2.98** / Calmar **3.40** / Max DD **-13.82%**
  - VaR (5%) **-1.95%** / CVaR (5%) **-2.86%**
  - 年率リターン **+47.03%** / 年率ボラ **+23.20%**
- スクリーンショット: `atr-usd-fix-verified.png` / `risk-metrics-panel-verified.png`（リポジトリ root、untracked）

---

## 2. 残タスク（優先順位付き）

### 🟡 優先 1: ATR Decision Log 連携 (#5)

- ATR 抵触時に `data/decision-log/{YYYY-MM}.jsonl` へ自動記録
- CLAUDE.md §9.5 / §9.8.3 規約準拠
- フィールド: `timestamp` / `action` / `ticker` / `shares` / `price_jpy` / `rationale` / `trigger.skill` / `trigger.metadata` / `stop_loss_atr_jpy` / `code_commit`
- 既存 `src/portfolio/decision_log.py` を活用
- 規模: 中（context ~50-70k 想定）

### 🟡 優先 2: 13F Cloning 動的化 (#4)

- `src/data/sec_edgar.py` の XML パーサ実装
- `src/data/famous_holdings.py` の静的辞書を SEC EDGAR からの動的取得に置換
- 13F-HR の四半期更新追従
- 規模: 大（context ~80-100k 想定）→ **フレッシュセッション推奨**

### ⚪ 副次: 7203.TO の EODHD 404 (#6)

- EODHD で `7203.TO` が 404 Not Found
- 東証は `.T` / `.JP` / `.TSE` のいずれかを要求している可能性
- 確認すべき: portfolio.csv の `exchange` 列、`Holding.ticker` 組み立てロジック、EODHDClient.get_eod の exchange パラメータ仕様
- 日本株は J-Quants 経由に分岐させる選択肢もあり
- 規模: 小（context ~20-30k 想定）

---

## 3. セッション開始時の自動アクション

```bash
cd /Users/kaori/Desktop/kaori_kabu

# 1. git 状況把握
git log --oneline -10
git status --short

# 2. テスト緑チェック
export PATH="$HOME/.local/bin:$PATH"
uv run pytest --no-cov -m "not slow" -q | tail -3
# 期待値: 270 passed, 3 deselected

# 3. 残タスクの再確認
cat .steering/20260509-phase-3-2-handoff/handoff.md
```

ユーザーへの最初の問いかけ（候補）:
> 「前回 Phase 3.2 リスク指標タブ独立化が完成 + 視覚検証 + 2 commit 済。残タスクは
> 🟡 #5 ATR Decision Log 連携 / 🟡 #4 13F Cloning 動的化 / ⚪ #6 7203.TO 404 修正。**どれから着手？**」

---

## 4. 動作確認済みコマンド

```bash
# テスト全体（slow 除く）
uv run pytest --no-cov -m "not slow" -q

# 特定モジュール
uv run pytest --no-cov -m "not slow" -q tests/unit/analysis/test_risk_metrics.py
uv run pytest --no-cov -m "not slow" -q tests/unit/dashboard/widgets/

# 構文チェック（全 .py）
uv run python -c "
import ast, glob
for f in glob.glob('src/**/*.py', recursive=True):
    ast.parse(open(f).read())
print('all files parse OK')
"

# Streamlit 起動 / 停止
uv run streamlit run src/dashboard/app.py --server.port 8520 --server.headless true
lsof -iTCP:8520 -sTCP:LISTEN
kill $(lsof -tiTCP:8520 -sTCP:LISTEN)
```

---

## 5. 既知の限界・注意（追記）

### Streamlit Markdown × KaTeX inline math 衝突（解決済み、知識として温存）

- `st.success` / `st.warning` / `st.error` / `st.markdown` は内部で KaTeX を使う
- `$...$` は inline math delimiter として解釈される
- USD 表示や金額に `$` を含めるときは `\$` でエスケープ必須
- 本セッションでは `_CURRENCY_SYMBOLS["USD"] = r"\$"` で対応
- 同様の罠は `_` での italic、バックスラッシュなど Markdown 特殊文字全般

### portfolio.csv サンプル

- 本セッションで `data/holdings/portfolio.csv` を **サンプル** (AAPL/US + 7203/TO) で作成
- `.gitignore` の `data/holdings/` で除外 → git には上がらない
- 本物の保有を入れる場合は内容を上書き or 新規追加（既存サンプルは破壊しないよう注意）

### 7203.TO の EODHD 404

- 副次タスク #6 として登録、未解決
- ATR / リスク指標は AAPL 単独で計算される（graceful degradation）

### ECC 自動メモリ

- `.omc/project-memory.json` に M がある場合、ECC が自動更新したもの
- コミットには含めない（毎セッション同じ）

### GateGuard hook

- Write/Edit 時に **facts 4 項目** を提示する必要:
  1. このファイルを import/require するコード
  2. 既存重複ファイル確認（Glob/Grep）
  3. データ I/O（フィールド・スキーマ・日付形式）
  4. ユーザー指示 verbatim
- Recovery: `ECC_GATEGUARD=off` 環境変数 or `pre:edit-write:gateguard-fact-force` を `ECC_DISABLED_HOOKS` に追加（ただしハードポリシー尊重で通常は facts 提示で対応）

---

## 6. 主要ファイルマップ（Phase 3.2 追加分）

```
src/analysis/risk_metrics.py                              — ★ 新規 純関数 + Provenance dataclass
src/dashboard/widgets/risk_metrics_panel.py               — ★ 新規 4×2 メトリクスグリッド
src/dashboard/views/01_home.py                            — Edit 評価結果直後にリスク指標セクション

tests/unit/analysis/test_risk_metrics.py                  — ★ 新規 12 ケース
tests/unit/dashboard/widgets/test_risk_metrics_panel.py   — ★ 新規 4 ケース

src/dashboard/widgets/atr_alert.py                        — Edit USD `$` → `\$` エスケープ
tests/unit/dashboard/widgets/test_atr_alert.py            — Edit 通貨別レンダリング 3 ケース追加

data/holdings/portfolio.csv                               — サンプル (AAPL/US + 7203/TO)、.gitignore 済
atr-usd-fix-verified.png                                  — 視覚検証 screenshot (untracked)
risk-metrics-panel-verified.png                           — 視覚検証 screenshot (untracked)
```

---

## 7. Streamlit 起動状態

- バックグラウンド起動: 本セッション task `b4p4an8hy` (port 8520) — セッション終了で停止する可能性
- ステータス確認: `lsof -iTCP:8520 -sTCP:LISTEN`
- 停止: `kill $(lsof -tiTCP:8520 -sTCP:LISTEN)`
- 新セッション開始時にプロセスが残ってる場合は kill して再起動推奨

---

## 8. 次セッション最初の操作（推奨）

1. このファイル `.steering/20260509-phase-3-2-handoff/handoff.md` を読む
2. `git status` + `git log --oneline -10` で現状確認（最新は `32e4130`）
3. テスト緑チェック (`pytest -m "not slow" -q | tail -3` で 270 passed 確認)
4. Streamlit が稼働中か確認、必要なら再起動
5. ユーザーに「優先 🟡 #5 ATR Decision Log / 🟡 #4 13F 動的化 / ⚪ #6 7203.TO — どれから着手？」と聞く

---

## 9. 学んだこと（再発防止メモ）

### Streamlit Markdown は KaTeX を含む

- `$...$` をエスケープしないと数式扱いされる
- 金額表示・通貨記号にこの罠がある
- `\$` でエスケープすると安全

### empyrical-reloaded の API（pin したい知識）

- `sharpe_ratio(returns, risk_free=0.0)` は **年率**
- `value_at_risk` / `conditional_value_at_risk` は `cutoff=` 引数で信頼区間
- すべて **daily simple returns (pct_change)** を入力前提
- 年率化は内部で 252 営業日係数

### Provenance 規約 (CLAUDE.md §9.8) の実運用

- 全 metric / signal / 判定に出所追跡情報必須
- 必須フィールド: `calculation_method` / `academic_source` / `input_data_period` / `code_commit`
- UI で expander 開示するパターンが第二脳化に効く（Confirmation Bias 抑止にもなる）
- regime.py / risk_metrics.py で同じ `_get_current_git_commit` パターンを 2 度実装 → Phase 3.2 後に `src/analysis/_provenance.py` 共通化候補

### Streamlit `@st.cache_data(ttl=...)` の挙動

- ttl 期間中は同一引数なら関数本体を呼ばない
- ファイル内容が変わっても、引数が同じならキャッシュヒット
- portfolio.csv 内容変更時は **Streamlit プロセス再起動が確実**
- または引数に `_arg` prefix で hash 除外可

### Playwright + Streamlit 注意点

- `wait_for "テキスト"` は Chrome 自動翻訳でテキストが書き換わると失敗する
- 例: 「最新価格で評価する」→「価格最新で評価する」と翻訳されて wait_for "最新価格" が timeout
- snapshot で実際の DOM を見て翻訳後文字列を確認するのが確実
- ナビゲート直後は同期的に snapshot を取らない（rerun 完了まで wait_for 必須）
